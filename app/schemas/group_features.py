from pydantic import BaseModel


class GroupFeatures(BaseModel):
    greeting_watch: bool = False
    kick_inactive_members: bool = False
    max_warning_count: int = 3
    report_new_members: bool = False
    report_leaving_members: bool = False