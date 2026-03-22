/**
 * ManuscriptView — renders OCR columns as a 稿紙 (manuscript paper) grid.
 *
 * Layout rules:
 * - Columns are displayed right-to-left (Chinese vertical writing order).
 * - Column 0 = rightmost column (first written column).
 * - Within each column, cells flow top-to-bottom; blank cells stay empty.
 * - Horizontal overflow scrolls from the right (direction: rtl).
 */

import type { ColumnData } from "../lib/types";

interface Props {
  columns: ColumnData[];
  /** Cell size in px (default 36). */
  cellSize?: number;
}

export default function ManuscriptView({ columns, cellSize = 36 }: Props) {
  if (columns.length === 0) return null;

  // Sort ascending — in RTL flex the first DOM element lands on the RIGHT,
  // so col_index 0 (rightmost paper column) will appear rightmost visually.
  const sorted = [...columns].sort((a, b) => a.col_index - b.col_index);

  return (
    // Outer: RTL + horizontal scroll — starts viewport from the right
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-gray-50 p-3" dir="rtl">
      {/* Inner: reset to LTR for text, but inherit RTL flex direction from parent */}
      <div className="inline-flex gap-0" dir="rtl">
        {sorted.map((col) => (
          <ColumnStrip key={col.col_index} col={col} cellSize={cellSize} />
        ))}
      </div>
    </div>
  );
}

function ColumnStrip({ col, cellSize }: { col: ColumnData; cellSize: number }) {
  // Normalise incoming indexes defensively. In some payloads values may be
  // stringified numbers and would fail Set.has(i) without conversion.
  const blankIndexes = (col.spacing_indexes ?? [])
    .map((v) => Number(v))
    .filter((v) => Number.isInteger(v) && v >= 0 && v < col.num_rows)
    .sort((a, b) => a - b);
  const blanks = new Set(blankIndexes);

  // Manuscript mode should use grid spacing as the single source of truth.
  // Drop OCR-emitted spaces/newlines to prevent off-by-one visual drift.
  const compactText = (col.text ?? "").replace(/[\s\u3000]+/g, "");
  // Spread into array so multi-byte / surrogate-pair chars remain one unit.
  const chars = [...compactText];
  let charIdx = 0;

  const cells: (string | null)[] = Array.from({ length: col.num_rows }, (_, i) => {
    if (blanks.has(i)) return null;
    return chars[charIdx++] ?? null;
  });

  return (
    <div
      className="flex flex-col border-l border-gray-300 first:border-l-0 last:border-l-0"
      style={{ width: cellSize }}
    >
      {cells.map((ch, i) => (
        <div
          key={i}
          className="flex shrink-0 items-center justify-center border-b border-gray-200 text-gray-900 last:border-b-0"
          style={{ width: cellSize, height: cellSize, fontSize: cellSize * 0.58 }}
          dir="ltr"
        >
          {ch}
        </div>
      ))}
    </div>
  );
}
