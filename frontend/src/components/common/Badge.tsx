import React from 'react';

export type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'luxury' | 'neutral';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
  icon?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  className = '',
  icon,
}) => {
  return (
    <span className={`ui-badge badge-${variant} ${className}`}>
      {icon && <span className="badge-icon" aria-hidden="true">{icon}</span>}
      <span className="badge-text">{children}</span>
    </span>
  );
};
