import React from 'react';
import type { AddOnItem } from '../../types';

interface AddOnSelectorProps {
  addOns: AddOnItem[];
  selectedIds: number[];
  onToggleAddOn: (addOn: AddOnItem) => void;
  disabled?: boolean;
}

export const AddOnSelector: React.FC<AddOnSelectorProps> = ({
  addOns,
  selectedIds,
  onToggleAddOn,
  disabled = false,
}) => {
  if (!addOns || addOns.length === 0) return null;

  return (
    <div className="addon-selector-card">
      <h4 className="addon-title">✦ Enhance Your Stay (Optional Add-ons)</h4>
      <div className="addon-list">
        {addOns.map((addon) => {
          const isSelected = selectedIds.includes(addon.id);
          return (
            <div
              key={addon.id}
              className={`addon-item ${isSelected ? 'addon-selected' : ''}`}
              onClick={() => !disabled && onToggleAddOn(addon)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  if (!disabled) onToggleAddOn(addon);
                }
              }}
              aria-pressed={isSelected}
              aria-disabled={disabled}
            >
              <div className="addon-checkbox">
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => {}}
                  disabled={disabled}
                  aria-label={`Select ${addon.name}`}
                />
              </div>

              <div className="addon-info">
                <div className="addon-name-row">
                  <span className="addon-name">{addon.name}</span>
                  <span className="addon-price">
                    ₹{addon.price.toLocaleString('en-IN')}{' '}
                    <small className="pricing-model">
                      ({addon.pricing_type.toLowerCase().replace(/_/g, ' ')})
                    </small>
                  </span>
                </div>
                {addon.description && (
                  <p className="addon-description">{addon.description}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
