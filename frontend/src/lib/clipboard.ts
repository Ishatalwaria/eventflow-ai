import { toast } from "sonner";

export async function copyToClipboard(value: string, successMessage: string) {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
    await navigator.clipboard.writeText(value);
    toast.success(successMessage);
    return true;
  } catch {
    toast.error("Clipboard access is unavailable.");
    return false;
  }
}
