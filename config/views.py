from django.http import JsonResponse


def home(request):
    return JsonResponse({
        "success": True,
        "message": "Welcome to KONNECT Virtual Classroom API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "admin": "/admin/",
            "accounts": "/api/",
        }
    })