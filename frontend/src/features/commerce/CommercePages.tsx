import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Filter, Package, ShoppingBag, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { apiErrorMessage } from "../../api/client";
import { commerceService } from "../../api/services/commerce";
import { useAuth } from "../../app/auth";
import { EmptyState, ErrorState, LoadingState, PageHeader, StateBadge } from "../../components/layout";
import { Button, Card } from "../../components/ui";
import { formatDate } from "../../lib/utils";

export function InventoryPage() {
  const { hasToken } = useAuth();
  const queryClient = useQueryClient();
  const [selectedClient, setSelectedClient] = useState<string>("all");

  const query = useQuery({
    queryKey: ["inventory"],
    queryFn: () => commerceService.inventory(),
    enabled: hasToken,
  });

  const seedMutation = useMutation({
    mutationFn: () => commerceService.seedDemoCatalog(),
    onSuccess: (data) => {
      toast.success(data.message || "Demo catalog seeded successfully.");
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
    onError: (err) => {
      toast.error(apiErrorMessage(err) || "Failed to seed demo catalog.");
    },
  });

  const allItems = query.data ?? [];

  // Extract distinct clients present in the inventory dataset
  const clientOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of allItems) {
      if (item.client_id) {
        map.set(item.client_id, item.client_name || item.client_id.slice(0, 8));
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [allItems]);

  // Filter items by selected client if not "all"
  const filteredItems = useMemo(() => {
    if (selectedClient === "all") return allItems;
    return allItems.filter((item) => item.client_id === selectedClient);
  }, [allItems, selectedClient]);

  const hasMultipleClients = clientOptions.length > 1;

  return (
    <>
      <PageHeader
        eyebrow="Catalog"
        title="Inventory"
        description="On-hand, reserved, and available stock per API client workspace."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => seedMutation.mutate()}
            disabled={seedMutation.isPending}
          >
            <Sparkles size={14} className="mr-1.5 text-amber-500" />
            {seedMutation.isPending ? "Seeding…" : "Seed Demo Catalog"}
          </Button>
        }
      />

      {!hasToken ? (
        <Card>
          <EmptyState
            icon={Package}
            title="API connection required"
            description="Sign in or connect a client token in Settings to view inventory."
          />
        </Card>
      ) : query.isLoading ? (
        <Card>
          <LoadingState label="Loading inventory…" />
        </Card>
      ) : query.isError ? (
        <ErrorState
          description={apiErrorMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : !allItems.length ? (
        <Card>
          <div className="p-8 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-blue-50 text-blue-600">
              <Package size={24} />
            </div>
            <h3 className="mt-3 text-sm font-bold text-slate-900">No products in catalog</h3>
            <p className="mt-1 text-xs text-slate-500">
              Your active workspace has no inventory items. Seed demonstration stock with one click.
            </p>
            <div className="mt-4">
              <Button
                size="sm"
                onClick={() => seedMutation.mutate()}
                disabled={seedMutation.isPending}
              >
                <Sparkles size={14} className="mr-1.5" />
                {seedMutation.isPending ? "Seeding demo catalog…" : "Seed Demo Catalog"}
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {hasMultipleClients && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50/60 p-3.5 text-xs">
              <div className="flex items-center gap-2 text-blue-900 font-medium">
                <Filter size={15} className="text-blue-600" />
                <span>Multi-Client Scope: Showing inventory across {clientOptions.length} workspaces</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500 font-medium">Filter workspace:</span>
                <select
                  value={selectedClient}
                  onChange={(e) => setSelectedClient(e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none"
                >
                  <option value="all">All Workspaces ({allItems.length} items)</option>
                  {clientOptions.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <Card className="overflow-hidden">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    {hasMultipleClients && <th>Workspace / Client</th>}
                    <th>SKU</th>
                    <th>Name</th>
                    <th>On hand</th>
                    <th>Reserved</th>
                    <th>Available</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((item) => (
                    <tr key={item.id}>
                      {hasMultipleClients && (
                        <td>
                          <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700 ring-1 ring-inset ring-blue-700/10">
                            {item.client_name || "Default Workspace"}
                          </span>
                        </td>
                      )}
                      <td className="font-mono">{item.sku}</td>
                      <td>{item.name}</td>
                      <td>{item.on_hand}</td>
                      <td>{item.reserved}</td>
                      <td>{item.available}</td>
                      <td>{formatDate(item.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

export function OrdersPage() {
  const { hasToken } = useAuth();
  const query = useQuery({ queryKey: ["orders"], queryFn: () => commerceService.orders(), enabled: hasToken });
  return (
    <>
      <PageHeader eyebrow="Commerce" title="Orders" description="Orders created by the fulfillment saga, including payment outcome." />
      {!hasToken ? <Card><EmptyState icon={ShoppingBag} title="API connection required" description="Connect a client token in Settings to view orders." /></Card> : query.isLoading ? <Card><LoadingState label="Loading orders…" /></Card> : query.isError ? <ErrorState description={apiErrorMessage(query.error)} onRetry={() => void query.refetch()} /> : !query.data?.length ? <Card><EmptyState icon={ShoppingBag} title="No orders yet" description="Submit an order.created event to start fulfillment." /></Card> : <Card className="overflow-hidden"><div className="table-scroll"><table className="data-table"><thead><tr><th>Order</th><th>Status</th><th>Total</th><th>Lines</th><th>Payment</th><th>Workflow</th></tr></thead><tbody>{query.data.map((order) => <tr key={order.id}><td className="font-mono">{order.external_order_id}</td><td><StateBadge state={order.status} /></td><td>{order.currency} {(order.total_minor_units / 100).toFixed(2)}</td><td>{order.lines.map((line) => line.sku + " × " + line.quantity).join(", ")}</td><td>{order.payments[0]?.status ?? "—"}{order.payments[0]?.failure_code ? " · " + order.payments[0].failure_code : ""}</td><td><Link className="font-mono text-blue-700 hover:underline" to={"/workflows/" + order.workflow_id}>{order.workflow_id.slice(0, 8)}</Link></td></tr>)}</tbody></table></div></Card>}
    </>
  );
}
