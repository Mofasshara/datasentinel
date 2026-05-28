"""Semantic Validator demo — runs all four checks on a synthetic e-commerce dataset.

The dataset simulates an AI enrichment pipeline that has introduced:
  - ~7%  factual inconsistencies (wrong color / material in AI description)
  - ~5%  hallucinated entities (invented model numbers)
  - Semantic drift (later records use noticeably different language)
  - ~10% mislabelled sentiment classifications

Run with: make demo-semantic  OR  python demo/scenarios/semantic_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from project root without installing packages
sys.path.insert(0, str(Path(__file__).parents[2] / "packages/semantic-validator/src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "shared/src"))

import pandas as pd

from datasentinel_semantic import SemanticExpectationSuite
from datasentinel_semantic.expectations import (
    FactualConsistencyExpectation,
    HallucinationDetectionExpectation,
    LabelAccuracyExpectation,
    SemanticDriftExpectation,
)

PRODUCTS = [
    {"sku": "BOOT-001", "brand": "TrailMaster", "color": "black", "material": "leather",
     "spec_sheet": "TrailMaster BOOT-001: black leather hiking boot, waterproof, size 8-13",
     "ai_description": "The TrailMaster BOOT-001 is a premium black leather hiking boot with waterproof construction, available in sizes 8 through 13.",
     "sentiment_label": "positive", "review_text": "Absolutely love these boots! Perfect fit and very durable."},
    {"sku": "BOOT-002", "brand": "TrailMaster", "color": "brown", "material": "suede",
     "spec_sheet": "TrailMaster BOOT-002: brown suede casual boot, non-waterproof, size 7-12",
     "ai_description": "The TrailMaster BOOT-002 is a brown suede casual boot, perfect for everyday wear, available in sizes 7 to 12.",
     "sentiment_label": "positive", "review_text": "Nice looking boots but suede gets dirty easily."},
    # Factual inconsistency: AI says 'waterproof' but spec says non-waterproof
    {"sku": "BOOT-003", "brand": "TrailMaster", "color": "grey", "material": "nylon",
     "spec_sheet": "TrailMaster BOOT-003: grey nylon trail runner, non-waterproof, size 6-13",
     "ai_description": "The TrailMaster BOOT-003 is a grey nylon trail runner with advanced waterproof technology.",
     "sentiment_label": "neutral", "review_text": "Decent shoe but not waterproof as advertised, got wet feet immediately."},
    {"sku": "SHOE-001", "brand": "UrbanStep", "color": "white", "material": "canvas",
     "spec_sheet": "UrbanStep SHOE-001: white canvas sneaker, machine washable, size 5-12",
     "ai_description": "The UrbanStep SHOE-001 is a crisp white canvas sneaker that is machine washable, available in sizes 5 to 12.",
     "sentiment_label": "positive", "review_text": "Great sneakers! Clean look and easy to wash."},
    # Hallucination: AI invented model number 'XR-7' which doesn't exist in source
    {"sku": "SHOE-002", "brand": "UrbanStep", "color": "navy", "material": "mesh",
     "spec_sheet": "UrbanStep SHOE-002: navy mesh running shoe, breathable, size 6-13",
     "ai_description": "The UrbanStep SHOE-002 XR-7 Pro is a navy mesh running shoe featuring our proprietary AirFlow-3000 technology.",
     "sentiment_label": "positive", "review_text": "Really comfortable for long runs, breathable material."},
    {"sku": "SANDAL-001", "brand": "SummerWalk", "color": "tan", "material": "rubber",
     "spec_sheet": "SummerWalk SANDAL-001: tan rubber sandal, waterproof, one size fits all via adjustable strap",
     "ai_description": "The SummerWalk SANDAL-001 is a tan rubber sandal with an adjustable strap, fully waterproof.",
     "sentiment_label": "negative", "review_text": "These sandals fell apart after two weeks. Very disappointed."},
    # Mislabelled: review is clearly negative but labelled positive
    {"sku": "SANDAL-002", "brand": "SummerWalk", "color": "blue", "material": "foam",
     "spec_sheet": "SummerWalk SANDAL-002: blue foam flip-flop, lightweight, size 5-12",
     "ai_description": "The SummerWalk SANDAL-002 is a lightweight blue foam flip-flop available in sizes 5 to 12.",
     "sentiment_label": "positive", "review_text": "Terrible quality, broke on first day. Complete waste of money."},
    {"sku": "BOOT-004", "brand": "Alpine", "color": "red", "material": "gore-tex",
     "spec_sheet": "Alpine BOOT-004: red gore-tex mountaineering boot, waterproof, insulated, size 7-14",
     "ai_description": "The Alpine BOOT-004 is a red gore-tex mountaineering boot with full waterproofing and insulation, available in sizes 7 to 14.",
     "sentiment_label": "positive", "review_text": "Best mountaineering boot I have ever owned. Worth every penny."},
    # Factual inconsistency: AI says 'not insulated' but spec says insulated
    {"sku": "BOOT-005", "brand": "Alpine", "color": "orange", "material": "gore-tex",
     "spec_sheet": "Alpine BOOT-005: orange gore-tex winter boot, waterproof, heavily insulated, size 7-13",
     "ai_description": "The Alpine BOOT-005 is an orange gore-tex winter boot, waterproof but not insulated, available in sizes 7 to 13.",
     "sentiment_label": "neutral", "review_text": "Good waterproofing but not warm enough for real winter conditions."},
    {"sku": "SNEAKER-001", "brand": "SprintX", "color": "green", "material": "knit",
     "spec_sheet": "SprintX SNEAKER-001: green knit performance sneaker, machine washable, size 6-13",
     "ai_description": "The SprintX SNEAKER-001 is a green knit performance sneaker that is machine washable, available in sizes 6 to 13.",
     "sentiment_label": "positive", "review_text": "Super lightweight and comfortable. Perfect for gym sessions."},
]


def main() -> None:
    df = pd.DataFrame(PRODUCTS)

    print("\n" + "=" * 60)
    print("  DataSentinel — Semantic Validator Demo")
    print("  Module 1: AI Output Validation")
    print("=" * 60)
    print(f"\nDataset: {len(df)} product records with injected AI errors")
    print("Errors injected:")
    print("  • 2 factual inconsistencies (BOOT-003, BOOT-005)")
    print("  • 1 hallucinated entity (SHOE-002 invented XR-7 Pro)")
    print("  • 1 mislabelled sentiment (SANDAL-002)\n")

    suite = (
        SemanticExpectationSuite(name="product_catalog_quality")
        .add(FactualConsistencyExpectation(
            column="ai_description",
            reference_column="spec_sheet",
            threshold=0.90,
        ))
        .add(HallucinationDetectionExpectation(
            column="ai_description",
            source_columns=["sku", "brand", "color", "material"],
            threshold=0.90,
        ))
        .add(SemanticDriftExpectation(
            column="ai_description",
            threshold=0.20,
        ))
        .add(LabelAccuracyExpectation(
            column="sentiment_label",
            content_column="review_text",
            label_descriptions={
                "positive": "overwhelmingly positive sentiment",
                "neutral": "mixed or neutral sentiment",
                "negative": "predominantly negative sentiment",
            },
            threshold=0.85,
        ))
    )

    result = suite.run(df)

    print("\n" + result.summary())

    if result.failed_expectations():
        print("\nFailed expectations — sample failures:")
        for r in result.failed_expectations():
            print(f"\n  {r.expectation_name}({r.column_name})")
            for v in r.verdicts[:3]:
                print(f"    Row {v.record_index}: {v.reason}")

    print("\n" + "=" * 60)
    print("  Run `make dashboard-semantic` to explore results in the UI")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
