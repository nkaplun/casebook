# Eval report, 2026-10-26

Model: `claude-haiku-5-5`

## Search: 13/13 passed

Median latency 3.4s. Tokens: 90,536 input (89,297 read from cache), 8,660 output.
Cost: $0.005 total, $0.0004 per question.

| Case | Result | Seconds | Notes |
|---|---|---|---|
| fintech-ml | pass | 5.1 |  |
| healthcare | pass | 4.5 |  |
| flutter | pass | 1.6 |  |
| client-name | pass | 2.0 |  |
| claude-api | pass | 5.2 |  |
| superlative-scale | pass | 4.0 |  |
| logistics-for-prospect | pass | 3.7 |  |
| no-match | pass | 1.7 |  |
| fabrication-trap | pass | 3.4 |  |
| no-relabeling | pass | 2.7 |  |
| deck-request | pass | 0.9 |  |
| deck-request-casual | pass | 1.1 |  |
| not-a-deck | pass | 6.6 |  |

## Deck: 3/3 passed

Median latency 15.1s. Tokens: 42,401 input (38,988 read from cache), 11,654 output.
Cost: $0.007 total, $0.0022 per question.

| Case | Result | Seconds | Notes |
|---|---|---|---|
| regional-bank | pass | 15.1 | first draft fixed after the check caught: case 2 (Loan Origination Platform Rebuild for a Digital Lender) metric 1 caption is 56 chars, over the 48 limit: 'Lower annual platform cost after retiring vendor license'; case 2 (Loan Origination Platform Rebuild for a Digital Lender) metric 3 caption is 55 chars, over the 48 limit: 'Downstream systems where manual re-entry was eliminated' |
| health-system | pass | 17.1 | first draft fixed after the check caught: case 2 (Customer Support Assistant for a Neobank) metric 1 caption is 51 chars, over the 48 limit: 'Tickets resolved with an approved draft, no rewrite' |
| retailer | pass | 14.3 | first draft fixed after the check caught: case 2 (Personalized Product Recommendations for an Outdoor Retailer) metric 2 caption is 50 chars, over the 48 limit: 'increase in repeat purchase rate over two quarters'; case 2 (Personalized Product Recommendations for an Outdoor Retailer) delivered item 2 is 111 chars, over the 110 limit: 'Model served through Vertex AI, tested in a six-week A/B test against hand-picked carousels before full rollout' |
