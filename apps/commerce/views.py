from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.commerce.models import InventoryItem, Order, PaymentIntent
from apps.common.models import APIClient
from apps.common.scope import get_effective_client, resolve_client_filter
from apps.workflows.models import Workflow
from apps.workflows.operations import (
    OperatorActionError,
    cancel_workflow,
    replay_workflow,
    retry_workflow,
)

from .serializers import (
    InventoryItemSerializer,
    OrderDetailSerializer,
    PaymentIntentSerializer,
)


class InventoryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = InventoryItem.objects.filter(
            resolve_client_filter(request, prefix="product__client")
        )
        client_id = request.query_params.get("client_id")
        if client_id:
            queryset = queryset.filter(product__client_id=client_id)
        items = queryset.select_related("product", "product__client").order_by(
            "product__client__name", "product__sku"
        )
        return Response(InventoryItemSerializer(items, many=True).data)


class SeedDemoCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.commerce.inventory import seed_demo_catalog_for_client

        target_client = None
        client_id = request.data.get("client_id")
        if client_id:
            target_client = get_object_or_404(
                APIClient.objects.filter(resolve_client_filter(request, prefix="")),
                pk=client_id,
            )
        else:
            target_client = get_effective_client(request)

        if not target_client:
            return Response(
                {"error": {"code": "NO_CLIENT", "message": "No active client found to seed."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        seed_demo_catalog_for_client(target_client)
        return Response(
            {
                "message": f"Demo catalog seeded for '{target_client.name}'.",
                "client_id": str(target_client.id),
                "client_name": target_client.name,
            },
            status=status.HTTP_200_OK,
        )


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Order.objects.filter(resolve_client_filter(request))
        workflow_id = request.query_params.get("workflow_id")
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)
        orders = queryset.prefetch_related("lines", "reservations", "payments").order_by(
            "-created_at"
        )[:100]
        return Response(OrderDetailSerializer(orders, many=True).data)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.filter(resolve_client_filter(request)).prefetch_related(
                "lines", "reservations", "payments"
            ),
            pk=order_id,
        )
        return Response(OrderDetailSerializer(order).data)


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id):
        payment = get_object_or_404(
            PaymentIntent.objects.filter(resolve_client_filter(request, prefix="order__client")),
            pk=payment_id,
        )
        return Response(PaymentIntentSerializer(payment).data)


class DeadLetterListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workflows = Workflow.objects.filter(
            resolve_client_filter(request, prefix="event__client"),
            state=Workflow.State.DEAD_LETTERED,
        ).order_by("-updated_at")[:100]
        return Response(
            [
                {
                    "workflow_id": str(workflow.id),
                    "workflow_type": workflow.workflow_type,
                    "current_stage": workflow.current_stage,
                    "last_error_code": workflow.last_error_code,
                    "updated_at": workflow.updated_at,
                }
                for workflow in workflows
            ]
        )


class WorkflowCommandView(APIView):
    permission_classes = [IsAuthenticated]
    action_name = ""

    def post(self, request, workflow_id):
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 255:
            return Response(
                {
                    "error": {
                        "code": "IDEMPOTENCY_KEY_REQUIRED",
                        "message": "Provide Idempotency-Key.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        workflow = get_object_or_404(
            Workflow.objects.filter(resolve_client_filter(request, prefix="event__client")),
            pk=workflow_id,
        )
        handler = {
            "retry": retry_workflow,
            "replay": replay_workflow,
            "cancel": cancel_workflow,
        }[self.action_name]
        try:
            workflow, log = handler(workflow=workflow, request=request, idempotency_key=key)
        except OperatorActionError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.detail}},
                status=exc.status,
            )
        return Response(
            {
                "workflow_id": str(workflow.id),
                "state": workflow.state,
                "current_stage": workflow.current_stage,
                "audit_id": str(log.id),
            }
        )


class WorkflowRetryView(WorkflowCommandView):
    action_name = "retry"

    @extend_schema(request=None, responses={200: dict})
    def post(self, request, workflow_id):
        return super().post(request, workflow_id)


class WorkflowReplayView(WorkflowCommandView):
    action_name = "replay"


class WorkflowCancelView(WorkflowCommandView):
    action_name = "cancel"
