"use client";

import * as React from "react";
import { ChevronDown, ChevronsUpDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Shared table primitive for the CRM list screens — the "heart of the CRM"
 * per the design brief. Bakes in the patterns every list re-implemented by
 * hand: sticky header, column sorting, mass selection (tri-state header
 * checkbox), skeleton loading and an empty state. Pages supply a `columns`
 * config + `rows`; cell rendering stays fully custom per page.
 *
 * Sorting is client-side over the *currently loaded* rows (these lists are
 * cursor-paginated, so it reorders what's on screen) — opt in per column by
 * providing `sortValue`.
 *
 * The table owns an internal scroll viewport (`overflow-auto` + max-height) so
 * the header can be truly sticky (`top-0`) — a plain `overflow-x-auto` wrapper
 * or an `overflow-hidden` Card ancestor would trap `position: sticky` and the
 * header would never stick. Short tables simply don't reach the max-height and
 * scroll with the page as before.
 */

export type SortDir = "asc" | "desc";

export type Column<T> = {
  id: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  align?: "left" | "right" | "center";
  /** Provide to enable client-side sorting on this column. */
  sortValue?: (row: T) => string | number | null | undefined;
  headerClassName?: string;
  cellClassName?: string;
  /** Tailwind width hint for the skeleton cell while loading. */
  skeletonClassName?: string;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  getRowId: (row: T) => string;
  loading?: boolean;
  skeletonRows?: number;
  /** Rendered (full width) when not loading and there are no rows. */
  empty?: React.ReactNode;
  minWidthClassName?: string;
  /** Height cap on the internal scroll viewport (enables the sticky header). */
  maxHeightClassName?: string;
  /** Mass-selection. Provide all three to turn the checkbox column on. */
  selectedIds?: Set<string>;
  onToggleRow?: (id: string) => void;
  onToggleAll?: () => void;
  selectAllLabel?: string;
  selectRowLabel?: string;
  onRowClick?: (row: T) => void;
};

const alignClass = (a?: "left" | "right" | "center") =>
  a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  loading = false,
  skeletonRows = 6,
  empty,
  minWidthClassName = "min-w-[40rem]",
  maxHeightClassName = "max-h-[calc(100dvh-13rem)]",
  selectedIds,
  onToggleRow,
  onToggleAll,
  selectAllLabel = "Select all",
  selectRowLabel = "Select row",
  onRowClick,
}: DataTableProps<T>) {
  const selectable = !!(selectedIds && onToggleRow && onToggleAll);
  const [sort, setSort] = React.useState<{ id: string; dir: SortDir } | null>(null);

  const sorted = React.useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.id === sort.id);
    if (!col?.sortValue) return rows;
    const factor = sort.dir === "asc" ? 1 : -1;
    // Copy before sort — never mutate the rows array the parent owns.
    return [...rows].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      // Nullish always sorts last regardless of direction.
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return -1 * factor;
      if (av > bv) return 1 * factor;
      return 0;
    });
  }, [rows, sort, columns]);

  function toggleSort(id: string) {
    setSort((prev) =>
      prev?.id === id ? (prev.dir === "asc" ? { id, dir: "desc" } : null) : { id, dir: "asc" },
    );
  }

  const allSelected = selectable && rows.length > 0 && selectedIds!.size === rows.length;
  const someSelected = selectable && selectedIds!.size > 0 && !allSelected;

  if (!loading && rows.length === 0 && empty) {
    return <>{empty}</>;
  }

  return (
    <div className={cn("overflow-auto", maxHeightClassName)}>
      <table className={cn("w-full text-sm", minWidthClassName)}>
        <thead className="sticky top-0 z-20 bg-muted/95 text-xs uppercase tracking-wider text-muted-foreground shadow-[inset_0_-1px_0_hsl(var(--border))] backdrop-blur supports-[backdrop-filter]:bg-muted/80">
          <tr>
            {selectable && (
              <th className="w-10 px-4 py-3 text-left font-medium">
                <Checkbox
                  aria-label={selectAllLabel}
                  checked={allSelected ? true : someSelected ? "indeterminate" : false}
                  onCheckedChange={onToggleAll}
                />
              </th>
            )}
            {columns.map((col) => {
              const active = sort?.id === col.id;
              return (
                <th
                  key={col.id}
                  className={cn(
                    "px-4 py-3 font-medium",
                    alignClass(col.align),
                    col.headerClassName,
                  )}
                >
                  {col.sortValue ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(col.id)}
                      className={cn(
                        "inline-flex items-center gap-1 transition-colors hover:text-foreground",
                        col.align === "right" && "flex-row-reverse",
                        active && "text-foreground",
                      )}
                    >
                      {col.header}
                      {active ? (
                        sort!.dir === "asc" ? (
                          <ChevronUp className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5" />
                        )
                      ) : (
                        <ChevronsUpDown className="h-3.5 w-3.5 opacity-40" />
                      )}
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={`sk-${i}`} className="border-t">
                  {selectable && (
                    <td className="px-4 py-3">
                      <Skeleton className="h-4 w-4 rounded" />
                    </td>
                  )}
                  {columns.map((col) => (
                    <td key={col.id} className={cn("px-4 py-3", alignClass(col.align))}>
                      <Skeleton className={cn("h-4 w-24", col.skeletonClassName)} />
                    </td>
                  ))}
                </tr>
              ))
            : sorted.map((row) => {
                const id = getRowId(row);
                const isSelected = selectable && selectedIds!.has(id);
                return (
                  <tr
                    key={id}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn(
                      "border-t transition-colors",
                      isSelected ? "bg-primary/5" : "hover:bg-muted/40",
                      onRowClick && "cursor-pointer",
                    )}
                  >
                    {selectable && (
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          aria-label={selectRowLabel}
                          checked={isSelected}
                          onCheckedChange={() => onToggleRow!(id)}
                        />
                      </td>
                    )}
                    {columns.map((col) => (
                      <td
                        key={col.id}
                        className={cn("px-4 py-3", alignClass(col.align), col.cellClassName)}
                      >
                        {col.cell(row)}
                      </td>
                    ))}
                  </tr>
                );
              })}
        </tbody>
      </table>
    </div>
  );
}
