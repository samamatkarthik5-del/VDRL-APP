from .request_context import (
    reset_current_request,
    set_current_request,
)


class CurrentRequestMiddleware:
    """
    Makes the current request available to the
    controlled audit signal handlers.
    """

    def __init__(
        self,
        get_response,
    ):
        self.get_response = (
            get_response
        )

    def __call__(
        self,
        request,
    ):
        token = set_current_request(
            request
        )

        try:
            response = self.get_response(
                request
            )

            return response

        finally:
            reset_current_request(
                token
            )