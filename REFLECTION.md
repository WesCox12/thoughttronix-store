## Featured Products

## Trace The Feature

A checkbox was created in the back office which allows the employees to mark a product as featured. A featured badge is displayed on the storefront catalog and product detail pages. Also CSS styling that makes the badge visible. 

## How I verified it

The agent reported 167 passing tests and used 'curl' to verify because chrome is not connected. It also temporarily marked 'calm collar' as featured to check and returned it to it's original state. I also manually went in and marked items as featured to test. I checked Seraphine, SoulSear Mark I and SoulSear Mark II.

## Judgement 

One challenge I encountered was that the featured field had been added to the product model, but I didn't find a change on the website. I learned that adding a database field does not automatically make it appear in a form. I had to request the agent to make a checkbox in the back office editor. 