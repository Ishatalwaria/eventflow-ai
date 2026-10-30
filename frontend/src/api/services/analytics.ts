/** Analytics are currently available only through the backend management command. */
export const analyticsService = {
  isAvailableThroughApi: false as const,
  unavailableReason: "The backend has no HTTP analytics endpoint. No report request is made from the browser.",
};
