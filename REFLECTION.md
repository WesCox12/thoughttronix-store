## Product Images

1 - Claude recommended cropping the images but I chose to use 800x800 with padding. I didn't want any of the images to be cut off. This resulted in losing no part of the artwork. 

2 -   File: products/models.py
    Line 138

    upload_to="products/" tells Django which subfolder inside MEDIA_ROOT should hold uploaded product images

 tags = models.ManyToManyField(Tag, blank=True, related_name="products")
    image = ProductImageField(
        upload_to="products/",
        blank=True,
        validators=[
            validate_usable_image,
            validate_image_format,
            validate_image_file_size,
            validate_image_dimensions,
        ],
    )

File: templates/products/manage_product_form.html
Line: 13
 <form method="post" enctype="multipart/form-data" class="mt-2 space-y-4">

 enctype="multipart/form-data" tells the browser to send the image file along with the other form fields. Without it, Django wouldn't receive the uploaded file properly.


 3 - Disk Location: C:\Users\Wesley Cox\cidm3312\thoughttronix-store\media\products\the-overthinker-9000.webp
     Database field value: products/the-overthinker-9000.webp
     Browser URL: http://127.0.0.1:8000/media/products/the-overthinker-9000.webp



## Featured Products

## Trace The Feature

A checkbox was created in the back office which allows the employees to mark a product as featured. A featured badge is displayed on the storefront catalog and product detail pages. Also CSS styling that makes the badge visible. 

## How I verified it

The agent reported 167 passing tests and used 'curl' to verify because chrome is not connected. It also temporarily marked 'calm collar' as featured to check and returned it to it's original state. I also manually went in and marked items as featured to test. I checked Seraphine, SoulSear Mark I and SoulSear Mark II.

## Judgement 

One challenge I encountered was that the featured field had been added to the product model, but I didn't find a change on the website. I learned that adding a database field does not automatically make it appear in a form. I had to request the agent to make a checkbox in the back office editor. 