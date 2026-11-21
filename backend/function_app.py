import logging

import azure.functions as func

from auth import Principal, json_response, require_auth


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return json_response({"status": "ok"})


@app.route(route="v1/auth-check", methods=["GET"])
@require_auth
def auth_check(req: func.HttpRequest, principal: Principal) -> func.HttpResponse:
    return json_response({"status": "authenticated"})


class ProcessingUnavailable(RuntimeError):
    pass


@app.queue_trigger(
    arg_name="message",
    queue_name="generation-jobs",
    connection="AzureWebJobsStorage",
)
def generation_worker(message: func.QueueMessage) -> None:
    logging.error("processing_unavailable: queue processing requires the issue #8 implementation")
    raise ProcessingUnavailable(
        "processing_unavailable: no processor is installed; retain the poison message "
        "and implement issue #8 before submitting jobs."
    )
