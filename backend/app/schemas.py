"""Pydantic request/response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .constants import (
    CAMERA_MODES,
    CHALLAN_STATUSES,
    DEMO_SOURCES,
    ROLES,
    VIOLATION_STATUSES,
    VIOLATION_TYPES,
)


# ------------------------------- auth ------------------------------------ #
class LoginRequest(BaseModel):
    user_id: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    role: str | None = None


class OtpRequestBody(BaseModel):
    user_id: str = Field(min_length=2, max_length=64)


class OtpVerifyBody(BaseModel):
    user_id: str
    otp: str = Field(min_length=4, max_length=8)


class ForgotPasswordBody(BaseModel):
    user_id: str


class ResetPasswordBody(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=128)


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


# ------------------------------- users ----------------------------------- #
class UserCreate(BaseModel):
    user_id: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    role: str = "officer"
    designation: str = ""
    phone: str = ""
    email: str = ""
    station: str = ""
    active: bool = True


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    designation: str | None = None
    phone: str | None = None
    email: str | None = None
    station: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


# ------------------------------ cameras ---------------------------------- #
class CameraCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    camera_id: str = Field(min_length=2, max_length=40)
    ip_address: str = ""
    rtsp_url: str = ""
    username: str = ""
    password: str = ""
    location: str = ""
    description: str = ""
    mode: Literal["LIVE", "DEMO"] = "DEMO"
    demo_source_type: Literal["SYNTHETIC", "VIDEO", "IMAGE"] = "SYNTHETIC"
    demo_source_path: str = ""
    enabled: bool = True
    detection_enabled: bool = True
    allowed_direction: Literal["ANY", "LEFT_TO_RIGHT", "RIGHT_TO_LEFT", "TOP_TO_BOTTOM", "BOTTOM_TO_TOP"] = "ANY"


class CameraUpdate(BaseModel):
    name: str | None = None
    ip_address: str | None = None
    rtsp_url: str | None = None
    username: str | None = None
    password: str | None = None
    location: str | None = None
    description: str | None = None
    mode: str | None = None
    demo_source_type: str | None = None
    demo_source_path: str | None = None
    enabled: bool | None = None
    detection_enabled: bool | None = None
    allowed_direction: str | None = None


class CameraToggle(BaseModel):
    enabled: bool


# ----------------------------- violations -------------------------------- #
class ViolationReviewBody(BaseModel):
    status: str
    remarks: str = ""
    plate_number: str | None = None


class ManualViolationBody(BaseModel):
    camera_id: str
    violation_type: str
    plate_number: str = ""
    confidence: float = 1.0
    remarks: str = ""


# ------------------------------ challans --------------------------------- #
class ChallanCreateBody(BaseModel):
    violation_id: str
    plate_number: str = ""
    fine_amount: float | None = None
    owner_name: str = ""
    owner_phone: str = ""
    send_sms: bool = True


class ChallanStatusBody(BaseModel):
    status: str
    remarks: str = ""


# ------------------------------ vehicles --------------------------------- #
class VehicleBody(BaseModel):
    plate_number: str = Field(min_length=4, max_length=20)
    owner_name: str = ""
    owner_phone: str = ""
    owner_address: str = ""
    vehicle_type: str = "Two Wheeler"
    make_model: str = ""
    colour: str = ""
    registration_date: str = ""
    insurance_valid_till: str = ""
    puc_valid_till: str = ""


# -------------------------------- rules ---------------------------------- #
class RuleBody(BaseModel):
    code: str
    label: str | None = None
    section: str | None = None
    fine_amount: float | None = None
    enabled: bool | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    auto_challan: bool | None = None
    description: str | None = None


# ------------------------------ payments --------------------------------- #
class PaymentInitBody(BaseModel):
    challan_id: str


class PaymentVerifyBody(BaseModel):
    challan_id: str
    razorpay_order_id: str = ""
    razorpay_payment_id: str = ""
    razorpay_signature: str = ""


# --------------------------------- sms ----------------------------------- #
class SmsTestBody(BaseModel):
    phone: str = Field(min_length=10, max_length=15)
    message: str = "Test SMS from RTO E-Challan System."


# ------------------------------ settings --------------------------------- #
class AppSettingsBody(BaseModel):
    rto_office_name: str | None = None
    rto_code: str | None = None
    state: str | None = None
    contact_number: str | None = None
    auto_challan: bool | None = None
    detection_interval_seconds: float | None = Field(default=None, ge=1, le=120)
    detection_cooldown_seconds: float | None = Field(default=None, ge=5, le=1800)
    detection_min_confidence: float | None = Field(default=None, ge=0, le=1)
    sms_on_challan: bool | None = None
    challan_due_days: int | None = Field(default=None, ge=1, le=180)


VALID_SETS = {
    "roles": ROLES,
    "camera_modes": CAMERA_MODES,
    "demo_sources": DEMO_SOURCES,
    "violation_types": VIOLATION_TYPES,
    "violation_statuses": VIOLATION_STATUSES,
    "challan_statuses": CHALLAN_STATUSES,
}
