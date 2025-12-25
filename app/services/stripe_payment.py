from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker
from stripe import StripeClient, InvalidRequestError

from app.config import settings


class StripePaymentService:
    def __init__(self):
        self.client = StripeClient(api_key=settings.STRIPE_API_KEY)

    async def get_product(self, product_id: str):
        try:
            product = self.client.v1.products.retrieve(product_id)
        except InvalidRequestError as e:
            logger.error(f"Invalid product id: {product_id}")
            raise e
        except Exception as e:
            logger.error(f"Failed to retrieve product {product_id}: {e}")
            raise e

        return product

    async def get_price(self, product_id: str):
        product = await self.get_product(product_id)
        try:
            price = self.client.v1.prices.retrieve(product.default_price)
        except InvalidRequestError as e:
            logger.error(f"Invalid price id: {product.default_price}")
            raise e
        except Exception as e:
            logger.error(f"Failed to retrieve price {product.default_price}: {e}")
            raise e

        return price.unit_amount

    async def create_payment_link(self, user_id: int, product_id: str):
        product = await self.get_product(product_id)
        logger.warning(product)
        if not product.active:
            raise ValueError(f"Product {product_id} is not active")

        payment_link = self.client.v1.payment_links.create(params={
            "line_items": [
                {
                    "price": product.default_price,
                    "quantity": 1
                }
            ],
            "metadata": {
                "user_id": str(user_id),
            }
        })
        logger.info(payment_link)

        return payment_link

    async def disable_payment_link(self, payment_link_id: str):
        try:
            self.client.v1.payment_links.update(payment_link_id, params={"active": False})
        except Exception as e:
            logger.error(f"Failed to disable payment link {payment_link_id}: {e}")
