import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearToken,
  getToken,
  isExpired,
  onTokenChange,
  readCookie,
  setToken,
} from "@/lib/auth";

function clearAllCookies() {
  for (const part of document.cookie.split("; ")) {
    const name = part.split("=")[0];
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }
}

beforeEach(() => {
  clearAllCookies();
});

afterEach(() => {
  clearAllCookies();
});

describe("readCookie", () => {
  it("returns the value of a present cookie", () => {
    document.cookie = "csrf_token=abc123";
    expect(readCookie("csrf_token")).toBe("abc123");
  });

  it("returns null for a missing cookie", () => {
    expect(readCookie("nope")).toBeNull();
  });

  it("URL-decodes the value", () => {
    document.cookie = `greeting=${encodeURIComponent("hi there")}`;
    expect(readCookie("greeting")).toBe("hi there");
  });

  it("does not match on a prefix collision", () => {
    document.cookie = "csrf_token_other=wrong";
    expect(readCookie("csrf_token")).toBeNull();
  });

  it("picks the right cookie among several", () => {
    document.cookie = "a=1";
    document.cookie = "csrf_token=tok";
    document.cookie = "b=2";
    expect(readCookie("csrf_token")).toBe("tok");
  });
});

describe("getToken", () => {
  it("returns the session sentinel when csrf_token cookie is present", () => {
    document.cookie = "csrf_token=present";
    expect(getToken()).toBe("cookie");
  });

  it("returns null when there is no csrf_token cookie", () => {
    expect(getToken()).toBeNull();
  });
});

describe("isExpired", () => {
  it("is true when there is no client-side session signal", () => {
    expect(isExpired(null)).toBe(true);
  });

  it("is false when a token signal is present", () => {
    expect(isExpired("cookie")).toBe(false);
  });
});

describe("listener bus", () => {
  it("setToken fans out the sentinel to subscribers", () => {
    const fn = vi.fn();
    onTokenChange(fn);
    setToken("ignored-value");
    expect(fn).toHaveBeenCalledWith("cookie");
  });

  it("clearToken fans out null to subscribers", () => {
    const fn = vi.fn();
    onTokenChange(fn);
    clearToken();
    expect(fn).toHaveBeenCalledWith(null);
  });

  it("onTokenChange returns an unsubscribe that stops further calls", () => {
    const fn = vi.fn();
    const unsubscribe = onTokenChange(fn);
    unsubscribe();
    setToken("x");
    clearToken();
    expect(fn).not.toHaveBeenCalled();
  });

  it("notifies multiple subscribers", () => {
    const a = vi.fn();
    const b = vi.fn();
    onTokenChange(a);
    onTokenChange(b);
    setToken("x");
    expect(a).toHaveBeenCalledWith("cookie");
    expect(b).toHaveBeenCalledWith("cookie");
  });
});
