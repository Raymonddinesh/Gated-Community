import React from 'react';

export const Table: React.FC<React.TableHTMLAttributes<HTMLTableElement>> = ({ className = '', children, ...props }) => (
  <div className="w-full overflow-x-auto rounded-lg border border-gray-200">
    <table className={`w-full text-left border-collapse text-sm text-gray-700 ${className}`} {...props}>
      {children}
    </table>
  </div>
);

export const TableHead: React.FC<React.HTMLAttributes<HTMLTableSectionElement>> = ({ className = '', children, ...props }) => (
  <thead className={`bg-gray-50 text-xs uppercase font-semibold text-gray-600 border-b border-gray-200 ${className}`} {...props}>
    {children}
  </thead>
);

export const TableBody: React.FC<React.HTMLAttributes<HTMLTableSectionElement>> = ({ className = '', children, ...props }) => (
  <tbody className={`divide-y divide-gray-200 bg-white ${className}`} {...props}>
    {children}
  </tbody>
);

export const TableRow: React.FC<React.HTMLAttributes<HTMLTableRowElement>> = ({ className = '', children, ...props }) => (
  <tr className={`hover:bg-gray-50 transition-colors ${className}`} {...props}>
    {children}
  </tr>
);

export const TableHeaderCell: React.FC<React.ThHTMLAttributes<HTMLTableCellElement>> = ({ className = '', children, ...props }) => (
  <th className={`px-4 py-3 font-semibold text-gray-900 ${className}`} scope="col" {...props}>
    {children}
  </th>
);

export const TableCell: React.FC<React.TdHTMLAttributes<HTMLTableCellElement>> = ({ className = '', children, ...props }) => (
  <td className={`px-4 py-3 text-gray-700 align-middle ${className}`} {...props}>
    {children}
  </td>
);
