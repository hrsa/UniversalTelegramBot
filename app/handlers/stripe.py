from fastapi import APIRouter, Request
from loguru import logger
from stripe import Webhook, SignatureVerificationError

from app.config import settings
from app.events.emitter import emit_event
from app.events.schemas import PaymentReceivedEvent

router = APIRouter()


@router.post("/stripe")
async def stripe_webhook(request: Request):
    headers = request.headers
    stripe_signature = headers.get("Stripe-Signature", None)

    try:
        event = Webhook.construct_event(payload=await request.body(), sig_header=stripe_signature, secret=settings.STRIPE_SIGNING_SECRET)
        if event.type == "checkout.session.completed":
            logger.warning(event)
            user_id = event.data.object.metadata.get("user_id", None)
            payment_id = event.data.object.payment_link
            amount = event.data.object.amount_total
            email = event.data.object.customer_details.email if event.data.object.customer_details.email else None
            await emit_event("payment_received", PaymentReceivedEvent(user_id=user_id, payment_link_id=payment_id, amount=amount, email=email))
    except ValueError:
        logger.error("Error while decoding event")
        return {"status": "Error while decoding event", "code": 400}
    except SignatureVerificationError:
        logger.error("Invalid signature")
        return {"status": "Invalid signature", "code": 401}
    return {"status": "OK"}