import api from "../client";
import type { EventAcceptance, EventBatchResponse, EventDetail, EventEnvelope, EventListItem, Paginated } from "../types";

export interface EventListParams {
  page?: number;
  page_size?: number;
  search?: string;
  event_type?: string;
  date_from?: string;
  date_to?: string;
}

export const eventsService = {
  async list(params: EventListParams = {}) {
    const response = await api.get<Paginated<EventListItem>>("/api/v1/events", { params });
    return response.data;
  },
  async create(envelope: EventEnvelope) {
    const response = await api.post<EventAcceptance>("/api/v1/events", envelope);
    return response.data;
  },
  async createBatch(events: EventEnvelope[]) {
    const response = await api.post<EventBatchResponse>("/api/v1/events/batch", { events });
    return response.data;
  },
  async get(eventId: string) {
    const response = await api.get<EventDetail>("/api/v1/events/" + encodeURIComponent(eventId));
    return response.data;
  },
};
