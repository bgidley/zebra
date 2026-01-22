"""Custom exception handlers for the Zebra Agent API."""

import logging

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Custom exception handler that provides consistent error responses."""
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Add extra detail for certain error types
        response.data["status_code"] = response.status_code
        return response

    # Handle unexpected exceptions
    logger.exception("Unhandled exception in API view")
    return Response(
        {
            "error": "Internal server error",
            "detail": str(exc),
            "status_code": 500,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
