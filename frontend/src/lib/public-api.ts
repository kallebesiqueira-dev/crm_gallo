// Public, UNAUTHENTICATED API surface (landing chatbot + public checkout).
// Kept separate from `lib/api.ts` (the authenticated client) on purpose: these
// calls send no cookies/credentials and need no CSRF token. Secrets never live
// here — only the public base URL, which is already exposed to the browser.

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ChatSource = "ai" | "fallback";

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatbotReply {
  message: string;
  source: ChatSource;
}

/**
 * Ask the public landing chatbot. Throws on network / non-2xx so the caller can
 * show an inline error + retry; the backend itself already degrades to a static
 * fallback (source: "fallback") rather than erroring on AI failure.
 */
export async function publicChatbot(
  message: string,
  history: ChatTurn[] = [],
  locale?: string,
  signal?: AbortSignal,
): Promise<ChatbotReply> {
  const res = await fetch(`${API_URL}/api/public/chatbot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, locale }),
    signal,
  });
  if (!res.ok) {
    throw new Error(`chatbot_request_failed_${res.status}`);
  }
  return (await res.json()) as ChatbotReply;
}

/**
 * Create a hosted Stripe Checkout session for a plan. The client sends ONLY the
 * plan key — the backend resolves + validates the price, so the amount can't be
 * tampered with. Returns the Checkout URL to redirect to.
 */
export async function createPublicCheckoutSession(
  plan: string,
  billingCycle: "monthly" | "yearly" = "monthly",
): Promise<string> {
  const res = await fetch(`${API_URL}/api/billing/create-checkout-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan, billing_cycle: billingCycle }),
  });
  if (!res.ok) {
    throw new Error(`checkout_request_failed_${res.status}`);
  }
  const data = (await res.json()) as { url: string };
  return data.url;
}
