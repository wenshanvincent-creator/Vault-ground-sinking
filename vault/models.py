from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["unknown", "inferred", "confirmed"] = "unknown"
    source: str = Field(default="", max_length=2000)
    confirmed_on: date | None = None
    confirmed_by: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def confirmation_has_basis(self):
        if self.status == "confirmed" and (not self.source.strip() or not self.confirmed_on or not self.confirmed_by.strip()):
            raise ValueError("确认资料时需填写依据、确认日期和确认人")
        return self


DeviceTopic = Literal["position", "axis", "height", "group", "installation", "connections", "cadence"]
ProfileTopic = Literal["layout", "ground_reference", "connections", "reference", "threshold", "timezone"]


class WarehouseProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ground_reference: str = Field(default="", max_length=3000)
    connections: str = Field(default="", max_length=3000)
    notes: str = Field(default="", max_length=3000)
    evidence: dict[ProfileTopic, Evidence] = Field(default_factory=dict)


class SiteEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_on: date
    event_type: Literal["load", "installation", "calibration", "collision", "maintenance", "other"]
    location: str = Field(min_length=1, max_length=300)
    members: list[str] = Field(default_factory=list, max_length=1000)
    description: str = Field(min_length=1, max_length=3000)
    recorded_by: str = Field(min_length=1, max_length=100)
    certainty: Literal["unknown", "inferred", "confirmed"] = "unknown"
    source: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def event_has_details(self):
        if any(not getattr(self, key).strip() for key in ("location", "description", "recorded_by")):
            raise ValueError("请填写位置、变更内容和记录人")
        if self.certainty == "confirmed" and not self.source.strip():
            raise ValueError("确认现场变更记录时请填写来源依据")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_start: str | None = None
    reference_days: int = Field(default=7, ge=2, le=90)
    angle_change_deg: float = Field(default=0.01, gt=0, le=30)
    trend_deg_week: float = Field(default=0.003, gt=0, le=30)
    consistency: float = Field(default=0.65, ge=0.5, le=1)
    min_day_coverage: float = Field(default=0.6, ge=0.1, le=1)
    common_correlation: float = Field(default=0.7, ge=0, le=1)
    angle_limit_deg: float | None = Field(default=None, gt=0, le=30)
    distance_limit_mm: float | None = Field(default=None, gt=0, le=10000)
    threshold_basis: str = Field(default="", max_length=1000)
    source_timezone: str = Field(default="未确认（按导出本地日期评估）", max_length=100)


class Device(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(default="", max_length=100)
    group: str = Field(default="", max_length=100)
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    height_mm: float | None = Field(default=None, gt=0, le=100000)
    expected_hours: float = Field(default=12, gt=0, le=8760)
    axis_confirmed: bool = False
    rotation_deg: float = Field(default=0, ge=-360, le=360)
    x_sign: Literal[-1, 1] = 1
    y_sign: Literal[-1, 1] = 1
    installed_on: date | None = None
    connections: str = Field(default="", max_length=2000)
    evidence: dict[DeviceTopic, Evidence] = Field(default_factory=dict)

    @model_validator(mode="after")
    def derive_axis_confirmation(self):
        self.axis_confirmed = "axis" in self.evidence and self.evidence["axis"].status == "confirmed"
        return self


class IssueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: str
    device_id: str
    reason: str = Field(min_length=1, max_length=2000)


class IssueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    status: Literal["pending", "inspection", "observing", "resolved"]
    note: str = Field(min_length=1, max_length=2000)
    author: str = Field(min_length=1, max_length=100)


class InspectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checked_on: date
    inspector: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=300)
    observation: str = Field(min_length=1, max_length=4000)
    action: str = Field(default="", max_length=3000)
    cause: str = Field(default="", max_length=2000)
    conclusion: Literal["unknown", "suspected", "confirmed"] = "unknown"
    basis: str = Field(default="", max_length=4000)
    follow_up: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def confirmed_requires_basis(self):
        for key in ("inspector", "location", "observation"):
            if not getattr(self, key).strip():
                raise ValueError("请填写检查人、位置和观察结果")
        if self.conclusion != "unknown" and not self.cause.strip():
            raise ValueError("请填写怀疑或确认的原因")
        if self.conclusion == "confirmed" and not self.basis.strip():
            raise ValueError("确认原因需填写测量或检查依据")
        return self


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ReportRequest(BaseModel):
    cycle: str = Field(default="week", pattern="^(week|month)$")
    cutoff: str | None = None
