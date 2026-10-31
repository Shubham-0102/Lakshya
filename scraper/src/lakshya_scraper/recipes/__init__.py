"""Recipes: a site's page structure saved as data, followed by plain code with no AI call."""

from lakshya_scraper.recipes.format import JobRules, ListingRules, Pick, Recipe
from lakshya_scraper.recipes.scraper import RecipeScraper

__all__ = ["JobRules", "ListingRules", "Pick", "Recipe", "RecipeScraper"]
