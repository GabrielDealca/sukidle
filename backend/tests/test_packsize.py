from decimal import Decimal

import pytest

from ingest.packsize import parse_pack_size

CASES = [
    # (input, size_value, size_unit, pack_count)
    ("Lucky Me Pancit Canton Original 60g x 6", "60", "g", 6),
    ("Lucky Me Pancit Canton Original 6 x 60g", "60", "g", 6),
    ("Lucky Me Pancit Canton 60gx6", "60", "g", 6),
    ("Lucky Me Pancit Canton 6x60g", "60", "g", 6),
    ("Nescafe Classic 50g", "50", "g", 1),
    ("Coca-Cola Regular 1.5L", "1.5", "L", 1),
    ("Coke Zero 1.5 L", "1.5", "L", 1),
    ("Pantene Conditioner 3 Minute Collagen Repair | 300ml", "300", "ml", 1),
    ("Alaska Evaporated Milk 370ml", "370", "ml", 1),
    ("Datu Puti Vinegar 1 Liter", "1", "L", 1),
    ("Silver Swan Soy Sauce 1 Litre", "1", "L", 1),
    ("Wilkins Distilled Water 500 mL x 24", "500", "ml", 24),
    ("San Miguel Pale Pilsen 330ml x 6 cans", "330", "ml", 6),
    ("Jasmine Rice 5kg", "5", "kg", 1),
    ("Dinorado Rice 25 kgs", "25", "kg", 1),
    ("Washed Sugar 1,000g", "1000", "g", 1),
    ("Bear Brand Powdered Milk Drink 33g x 12s", "33", "g", 12),
    ("Milo Activ-Go 24g 10s", "24", "g", 10),
    ("Kopiko Brown Coffee 10 sachets x 25g", "25", "g", 10),
    ("Great Taste White 30g 10 sachets", "30", "g", 10),
    ("Magic Sarap 8g x 12 tie-pack", "8", "g", 12),
    ("Knorr Sinigang sa Sampalok Mix 22g 12 tie packs", "22", "g", 12),
    ("Fresh Eggs Large 12pcs", "12", "pcs", 1),
    ("Fresh Eggs Medium 30 pcs", "30", "pcs", 1),
    ("Sanicare Bathroom Tissue 2ply 12 rolls", "12", "roll", 1),
    ("Safeguard Pure White Bar Soap 135g x 3", "135", "g", 3),
    ("Colgate Toothpaste 150g 6+1pcs", "150", "g", 7),
    ("Pringles Original 6+1pcs", "7", "pcs", 1),
    ("Banana Lakatan 1000g-1500g", "1000", "g", 1),
    ("Pork Liempo 500-700g", "500", "g", 1),
    ("Nido Fortigrow 1.6kg", "1.6", "kg", 1),
    ("Gatorade Blue Bolt 500ml", "500", "ml", 1),
    ("Biogesic Paracetamol 500mg 20 tablets", "500", "mg", 20),
    ("Surf Powder Detergent 2.1kg", "2.1", "kg", 1),
    ("Downy Fabric Conditioner 36ml x 24 sachets", "36", "ml", 24),
    ("C2 Green Tea Apple 230ml x 6", "230", "ml", 6),
    ("Lucky Me Instant Mami Beef 55g Pack of 6", "55", "g", 6),
    ("NEW! Oishi Prawn Crackers 60g", "60", "g", 1),
    ("Del Monte Pineapple Juice 1.36L", "1.36", "L", 1),
    ("Purefoods Tender Juicy Hotdog 1kg", "1", "kg", 1),
    ("Jack n Jill Piattos Cheese 85 g", "85", "g", 1),
    ("Novellino Rosso Wine 750 ML", "750", "ml", 1),
    ("Tide Bar Original 4 x 125g", "125", "g", 4),
    ("Dove Shampoo 12ml-6pcs", "12", "ml", 6),
    ("Pampers Baby Dry Pants Large 40s", "40", "pcs", 1),
    ("Fita Crackers 30g x 10 packs", "30", "g", 10),
    ("Royal Tru-Orange 8oz", "8", "oz", 1),
    ("Spam Classic 340 grams", "340", "g", 1),
    ("Nescafe 3-in-1 Original 20g x 30", "20", "g", 30),
    ("Del Monte Spaghetti Sauce 1kg x 2", "1", "kg", 2),
    ("7-Up Lemon Lime 1.5L", "1.5", "L", 1),
    ("300ml", "300", "ml", 1),
    ("Hansel Mocha Sandwich 10 x 32g", "32", "g", 10),
    ("Zonrox Bleach 1gal", None, "", 1),  # gallons not supported -> empty
]


@pytest.mark.parametrize(("text", "value", "unit", "pack"), CASES)
def test_parse_pack_size(text, value, unit, pack):
    result = parse_pack_size(text)
    assert result.size_value == (Decimal(value) if value is not None else None), text
    assert result.size_unit == unit, text
    assert result.pack_count == pack, text


@pytest.mark.parametrize(
    "text", ["", "Rocky Road Ice Cream", "Buy 1 Take 1 Fudgee Barr", "Large Brown Eggs"]
)
def test_no_size(text):
    result = parse_pack_size(text)
    assert result.size_value is None
    assert result.size_text == ""


def test_size_text_is_canonical():
    assert parse_pack_size("Pancit Canton 6 x 60g").size_text == "60g x 6"
    assert parse_pack_size("Coke 1.50 L").size_text == "1.5L"
    assert parse_pack_size("Rice 100kg").size_text == "100kg"


def test_at_least_40_real_world_cases():
    assert len(CASES) >= 40
