import api from "../client";
import type { EventAcceptance, EventBatchResponse, EventDetail, EventEnvelope } from "../types";

export const eventsService = {
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
