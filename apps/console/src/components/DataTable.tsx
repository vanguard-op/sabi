import type { ReactNode } from 'react';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Enables a sort control on the header; returns the comparable value. */
  sortValue?: (row: T) => string | number;
  width?: string;
}

export interface TableSort {
  key: string;
  direction: 'asc' | 'desc';
}

/**
 * The console's primary surface: an accessible data table with optional
 * column sorting, hover and selected states from the token set, and a keyboard
 * focus ring that uses the inset variant inside the scroll container.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  getRowId,
  sort,
  onSort,
  selectedId,
  onSelect,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  getRowId: (row: T) => string;
  sort?: TableSort | undefined;
  onSort?: ((key: string) => void) | undefined;
  selectedId?: string | undefined;
  onSelect?: ((row: T) => void) | undefined;
}): JSX.Element {
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((col) => {
              const sortable = Boolean(col.sortValue && onSort);
              const active = sort?.key === col.key;
              return (
                <th
                  key={col.key}
                  scope="col"
                  style={col.width ? { width: col.width } : undefined}
                  aria-sort={
                    active ? (sort?.direction === 'asc' ? 'ascending' : 'descending') : 'none'
                  }
                >
                  {sortable ? (
                    <button
                      type="button"
                      className="table-sort focus-inset"
                      data-active={active}
                      onClick={() => onSort?.(col.key)}
                    >
                      {col.header}
                      <span aria-hidden="true">{active ? (sort?.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
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
          {rows.map((row) => {
            const id = getRowId(row);
            const selected = selectedId === id;
            return (
              <tr
                key={id}
                aria-selected={selected}
                onClick={onSelect ? () => onSelect(row) : undefined}
                style={onSelect ? { cursor: 'pointer' } : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key} className={col.key === 'actions' ? 'cell-actions' : undefined}>
                    {col.render(row)}
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
