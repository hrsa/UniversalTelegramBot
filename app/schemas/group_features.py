from pydantic import BaseModel


class ChannelFeatures(BaseModel):
    report_new_members: bool = False
    report_leaving_members: bool = False
    allow_payments: bool = False

class GroupFeatures(ChannelFeatures):
    greeting_watch: bool = False
    kick_inactive_members: bool = False
    max_warning_count: int = 3