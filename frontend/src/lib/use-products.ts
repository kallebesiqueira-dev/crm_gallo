"use client";

/**
 * TanStack Query hooks for the Products/Services list. Simpler than the other
 * lists — products carry no tags/segments, so it's just a cursor list plus a
 * delete mutation.
 */

import { keepPreviousData, useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Page, type Product } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const productsKeys = {
  all: ["products"] as const,
  list: (q: string) => ["products", "list", { q }] as const,
};

/** Cursor-paginated products list, optionally filtered by a search string. */
export function useProductsInfinite(q: string) {
  const token = getToken();
  return useInfiniteQuery<Page<Product>>({
    queryKey: productsKeys.list(q),
    enabled: !!token,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.listProducts(token as string, {
        q: q || undefined,
        cursor: pageParam as string | undefined,
      }),
    getNextPageParam: (last) => (last.has_more ? (last.next_cursor ?? undefined) : undefined),
    placeholderData: keepPreviousData,
  });
}

/** Soft-delete a product, then invalidate every products list so it drops out. */
export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProduct(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: productsKeys.all }),
  });
}
