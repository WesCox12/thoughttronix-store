## 1. The Apps and What Each Owns
accounts, dashboard, orders, products

Accounts - The accounts app defines the store's users, customers, employees, and administrators. 

Dashboard - The dashboard app provides a sales analytics page for employees. Revenue tracking, order statistics, top products, date filtering, and access control.

Orders - The orders app manages the shopping cart and purchasingn process. There are four models. Cart, CartItem, Order, OrderItem. 

Products - The products app manages the stores product catalog. Including categories, tags, prices, availability, and product searches. 

## 2. The Path of One Request

When someone visits the homepage, Django starts in config/urls.py, which includes the routes from products/urls.py. 

## 3. A Model I Read

The cart model is connected to a user's account. add() checks whether a product is already in the cart and increases quantity instead of creating a duplicate entry.

## 4. Deleting a Category

Django prevents deletion if products are still assigned to it. Product uses on_delete=models.PROTECT in the ForeignKey which prevents deletion. 

## 5. Where the Tests Live

The product uses pytest to test user registration, login, and logout. conftest.py will create test users, categories, and shopping carts so the tests can reuse them. 

## 6. Something I'm Still Working to Understand

I'm not entirely confident on my understanding of how pytest features are shared between tests. 