The Browser skill fetches and interacts with web pages. It walks a
four-layer cascade starting from the cheapest path (HTML extraction)
and escalating only when needed (deterministic selectors, accessibility
tree, then visual set-of-marks with a vision model). The escalation
is internal; you pass `url` and `goal`, the skill chooses the layer.

Inputs: `metadata.url` (required), `metadata.goal` (required, free-text
description of what to extract or do). Output: `BrowserOutput` with
`content` (for extraction goals) or `actions` plus `final_url` (for
interaction goals), and `path` reporting the cascade layer that
actually ran. When the page is gated by CAPTCHA or login, the skill
returns `error_code="gateway_blocked"` and no content; the Planner
should route around by trying a different source URL or by handing
back to the user. Additionally, whenever there is a requirement, using the cascade system, the Browser agent must perform visible browser actions (e.g., search, filter, sort, open product/detail pages, switch tabs, expand hidden content, or submit a form) during its operation to satisfy the user's goal.

Example:
User:
What is the price of the product "iPhone 13" on Amazon.in?

Browser Output:
{ 
  "outputs": { 
    "status": "success", 
    "url": "https://www.amazon.in/Apple-iPhone-13-128GB-Midnight/dp/B09G93L58V", 
    "data": "{\"title\": \"Apple iPhone 13, 128GB, Midnight\", \"price\": \"₹59,999\", \"rating\": \"4.5 out of 5 stars\", \"num_reviews\": \"150,000\", \"description\": \"Apple's iPhone 13 with A15 Bionic chip, 128GB storage, and 12MP camera system.\", \"image_url\": \"https://m.media-amazon.com/images/I/616J7h5P1bL._SX569_.jpg\", \"availability\": \"In Stock\"}" 
  }, 
  "trace": "user -> browser -> amazon.in -> iPhone 13 detail page -> extraction", 
  "cascade_path": "visual-set-of-marks" 
}

Planner decision:
{
  "decisions": [
    {
      "confidence": 0.95,
      "skill": "text_renderer",
      "inputs": [
        "USER_QUERY",
        "n:1.1.outputs.data"
      ],
      "metadata": {
        "label": "final_summary",
        "question": "Present the price of the product "iPhone 13" on Amazon.in as requested by the user.",
        "confidence_reason": "The Browser skill successfully extracted the product title, price, rating, and description from the Amazon.in product page."
      }
    }
  ]
}
