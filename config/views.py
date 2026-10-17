from django.http import JsonResponse
from django.urls import reverse


def home(request):
    return JsonResponse({
        "success": True,
        "message": "Welcome to KONNECT Virtual Classroom API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "admin": "/admin/",
            "accounts": "/api/",
        },
        "documentation": {
            "swagger": request.build_absolute_uri(reverse("swagger-ui")),
            "redoc": request.build_absolute_uri(reverse("redoc")),
            "openapi_schema": request.build_absolute_uri(reverse("schema")),
        },
    })
