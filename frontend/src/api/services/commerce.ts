import api from "../client";

export interface InventoryRow {
  id: string;
  client_id?: string;
  client_name?: string;
  sku: string;
  name: string;
  on_hand: number;
  reserved: number;
  available: number;
  updated_at: string;
}

export interface ReservationRow {
  id: string;
  sku: string;
  quantity: number;
  status: string;
  created_at: string;
}

export interface OrderRow {
  id: string;
  workflow_id: string;
  event_id: string;
  external_order_id: string;
  currency: string;
  total_minor_units: number;
  status: string;
  failure_code: string;
  created_at: string;
  updated_at: string;
  lines: Array<{ sku: string; quantity: number; unit_price_minor: number }>;
  reservations?: ReservationRow[];
  payments: Array<{ id: string; status: string; failure_code: string; amount_minor: number; provider: string }>;
}

export const commerceService = {
  async inventory(params?: { client_id?: string }) {
    const response = await api.get<InventoryRow[]>("/api/v1/inventory", { params });
    return response.data;
  },
  async seedDemoCatalog(clientId?: string) {
    const response = await api.post<{ message: string; client_id: string; client_name: string }>(
      "/api/v1/seed-catalog",
      { client_id: clientId }
    );
    return response.data;
  },
  async orders(params?: { workflow_id?: string }) {
    const response = await api.get<OrderRow[]>("/api/v1/orders", { params });
    return response.data;
  },
};
