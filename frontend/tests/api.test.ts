import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, setUnauthorizedHandler } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Body = unknown;

function mockResponse(status: number, body: Body = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    statusText: `status ${status}`,
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  };
}

const fetchMock = vi.fn();

// Let one queued macrotask run, so the singleton-refresh `setTimeout(0)`
// that clears `refreshInFlight` fires before the next test starts.
const flushMacrotask = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  setUnauthorizedHandler(null);
  for (const part of document.cookie.split("; ")) {
    const name = part.split("=")[0];
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }
});

afterEach(async () => {
  await flushMacrotask();
  vi.unstubAllGlobals();
});

describe("request() headers", () => {
  it("sends Content-Type json + credentials:include on every call", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "l1" }));
    await api.getLead("tok", "l1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/leads/l1`);
    expect(init.credentials).toBe("include");
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("does NOT attach X-CSRF-Token on a safe (GET) method", async () => {
    document.cookie = "csrf_token=secret";
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "l1" }));
    await api.getLead("tok", "l1");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("mirrors the csrf_token cookie into X-CSRF-Token on a mutating method", async () => {
    document.cookie = "csrf_token=secret";
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "l1" }));
    await api.createLead("tok", { first_name: "A" });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers["X-CSRF-Token"]).toBe("secret");
  });

  it("omits X-CSRF-Token on a mutating method when the cookie is absent", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "l1" }));
    await api.createLead("tok", { first_name: "A" });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["X-CSRF-Token"]).toBeUndefined();
  });
});

describe("optimistic locking (If-Match)", () => {
  it.each([
    ["updateCustomer", () => api.updateCustomer("tok", "c1", { company: "Acme" }, 3)],
    ["updateDeal", () => api.updateDeal("tok", "d1", { stage: "qualified" }, 3)],
    ["updateTask", () => api.updateTask("tok", "t1", { status: "done" }, 3)],
  ])("%s sends If-Match with the passed version", async (_name, call) => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "x", version: 4 }));
    await call();
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PATCH");
    expect(init.headers["If-Match"]).toBe("3");
  });

  it("moveDeal forwards the deal version as If-Match", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "d1", version: 5 }));
    await api.moveDeal("tok", "d1", "qualified", 2, 4);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/deals/d1/move`);
    expect(init.method).toBe("POST");
    expect(init.headers["If-Match"]).toBe("4");
  });

  it("omits If-Match when no version is passed (server stays v1-lenient)", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "c1", version: 1 }));
    await api.updateCustomer("tok", "c1", { company: "Acme" });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["If-Match"]).toBeUndefined();
  });

  it("sends If-Match:'0' for a freshly-created row (version 0 is truthy-safe)", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "t1", version: 1 }));
    await api.updateTask("tok", "t1", { status: "done" }, 0);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["If-Match"]).toBe("0");
  });

  it("surfaces a 412 as an ApiError the UI can branch on", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(412, { detail: "version mismatch" }));
    await expect(api.updateCustomer("tok", "c1", { company: "Acme" }, 1)).rejects.toMatchObject({
      name: "ApiError",
      status: 412,
    });
  });
});

describe("request() responses", () => {
  it("returns parsed json on 200", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { id: "l1", first_name: "Ann" }));
    const lead = await api.getLead("tok", "l1");
    expect(lead).toEqual({ id: "l1", first_name: "Ann" });
  });

  it("returns undefined on 204 without calling json()", async () => {
    const resp = mockResponse(204);
    const jsonSpy = vi.spyOn(resp, "json");
    fetchMock.mockResolvedValueOnce(resp);
    const result = await api.deleteLead("tok", "l1");
    expect(result).toBeUndefined();
    expect(jsonSpy).not.toHaveBeenCalled();
  });

  it("throws ApiError carrying status + json detail on a 4xx", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(400, { detail: "Bad name" }));
    await expect(api.getLead("tok", "l1")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      message: "Bad name",
    });
  });

  it("falls back to response text when the error body is not json", async () => {
    const resp = mockResponse(500, "boom");
    resp.json = async () => {
      throw new Error("not json");
    };
    fetchMock.mockResolvedValueOnce(resp);
    await expect(api.getLead("tok", "l1")).rejects.toMatchObject({
      status: 500,
      message: "boom",
    });
  });
});

describe("401 refresh flow", () => {
  it("on 401, refreshes once and retries the original request", async () => {
    fetchMock
      .mockResolvedValueOnce(mockResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(mockResponse(200, {})) // /refresh
      .mockResolvedValueOnce(mockResponse(200, { id: "u1" })); // retry /me

    const user = await api.me("tok");
    expect(user).toEqual({ id: "u1" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe(`${API_URL}/api/auth/refresh`);
  });

  it("forwards the csrf_token to /refresh as X-CSRF-Token", async () => {
    document.cookie = "csrf_token=csrf1";
    fetchMock
      .mockResolvedValueOnce(mockResponse(401))
      .mockResolvedValueOnce(mockResponse(200, {}))
      .mockResolvedValueOnce(mockResponse(200, { id: "u1" }));
    await api.me("tok");
    const refreshInit = fetchMock.mock.calls[1][1];
    expect(refreshInit.method).toBe("POST");
    expect(refreshInit.headers["X-CSRF-Token"]).toBe("csrf1");
  });

  it("when refresh fails: clears session, calls the unauthorized handler, throws ApiError(401)", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock
      .mockResolvedValueOnce(mockResponse(401))
      .mockResolvedValueOnce(mockResponse(401)); // /refresh also 401 → not ok

    await expect(api.me("tok")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Session expired",
    });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    // initial + one refresh attempt, no retry
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not attempt a second refresh loop if the retry also 401s", async () => {
    setUnauthorizedHandler(vi.fn());
    fetchMock
      .mockResolvedValueOnce(mockResponse(401)) // initial
      .mockResolvedValueOnce(mockResponse(200, {})) // refresh ok
      .mockResolvedValueOnce(mockResponse(401)); // retry still 401

    await expect(api.me("tok")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(3); // initial, refresh, retry — then give up
  });

  it("coalesces concurrent 401s into a single /refresh call", async () => {
    let meCount = 0;
    let refreshCount = 0;
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/api/auth/refresh")) {
        refreshCount += 1;
        return Promise.resolve(mockResponse(200, {}));
      }
      meCount += 1;
      // First two hits are the two concurrent initial calls → expire them.
      if (meCount <= 2) return Promise.resolve(mockResponse(401));
      return Promise.resolve(mockResponse(200, { id: "u1" }));
    });

    const [a, b] = await Promise.all([api.me("tok"), api.me("tok")]);
    expect(a).toEqual({ id: "u1" });
    expect(b).toEqual({ id: "u1" });
    expect(refreshCount).toBe(1);
  });
});

describe("login()", () => {
  it("posts form-urlencoded credentials with credentials:include", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(200, { user: {}, token: {} }));
    await api.login("a@b.com", "pw");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/auth/login`);
    expect(init.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
    expect(init.credentials).toBe("include");
    expect(init.body).toContain("username=a%40b.com");
  });

  it("maps a 429 to a friendly ApiError", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(429, { detail: "rate" }));
    await expect(api.login("a@b.com", "pw")).rejects.toMatchObject({
      status: 429,
      message: "Too many attempts. Try again shortly.",
    });
  });

  it("surfaces the server detail on a failed login", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(401, { detail: "Invalid credentials" }));
    await expect(api.login("a@b.com", "pw")).rejects.toMatchObject({
      status: 401,
      message: "Invalid credentials",
    });
  });
});
