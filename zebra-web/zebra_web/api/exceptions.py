"""Custom exception handling for the Zebra API."""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """Custom exception handler that provides consistent error responses."""
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Customize the response data
        response.data = {
            "error": True,
            "message": get_error_message(response.data),
            "status_code": response.status_code,
            "details": response.data if isinstance(response.data, dict) else None,
        }
    else:
        # Handle unexpected exceptions
        response = Response(
            {
                "error": True,
                "message": str(exc),
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "details": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def get_error_message(data):
    """Extract a human-readable error message from response data."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return data[0] if data else "An error occurred"
    if isinstance(data, dict):
        if "detail" in data:
            return data["detail"]
        if "message" in data:
            return data["message"]
        # Try to get first error message from field errors
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            if isinstance(value, str):
                return f"{key}: {value}"
    return "An error occurred"
