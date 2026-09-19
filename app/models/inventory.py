"""Optional inventory items. The marketplace works fine with zero of these."""
from typing import Dict, Optional

from app.models.user import utcnow
from app.utils.parsing import normalize_text


def product_key(name: str) -> str:
    """Stable lookup key so 'Teflon Tape' and 'teflon  tape' collapse together."""
    return normalize_text(name).lower()


def build_inventory_document(
    *, shop_id, product: str, quantity: float = 0, unit: str = "piece",
    brand: Optional[str] = None, price: Optional[float] = None,
    source: str = "manual", confidence: float = 1.0,
) -> Dict:
    now = utcnow()
    return {
        "shop_id": shop_id,
        "product": normalize_text(product),
        "product_key": product_key(product),
        "quantity": float(quantity or 0),
        "unit": unit or "piece",
        "brand": brand,
        "price": price,
        "source": source,  # manual | voice | invoice_image | shelf_image
        "confidence": confidence,
        "created_at": now,
        "updated_at": now,
    }
