from app.handlers.common import router as common_router
from app.handlers.member_watch import router as member_watch_router
from app.handlers.group_interactions import router as group_interactions_router
from app.handlers.admin.admin_interactions import router as admin_interactions_router
from app.handlers.admin.greeting_watch import router as greeting_watch_router
from app.handlers.admin.manage_announcement import router as manage_announcement_router
from app.handlers.admin.create_announcement import router as create_announcement_router
from app.handlers.message_interactions import router as message_interactions_router


all_routers = [common_router, member_watch_router, group_interactions_router, admin_interactions_router,
               message_interactions_router, greeting_watch_router, manage_announcement_router, create_announcement_router]