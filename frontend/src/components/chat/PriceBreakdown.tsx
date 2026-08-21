import React from 'react';

export interface PriceBreakdownAddOn {
  id: number;
  name: string;
  price: number;
  pricing_type: string;
  total?: number;
}

export interface PriceBreakdownData {
  room_name: string;
  property_name?: string;
  nights: number;
  base_rate_per_night: number;
  room_subtotal: number;
  add_ons?: PriceBreakdownAddOn[];
  add_ons_total?: number;
  tax_and_fees?: number;
  total_price: number;
}

interface PriceBreakdownProps {
  data: PriceBreakdownData;
  onProceedToHold?: () => void;
  canHold?: boolean;
}

export const PriceBreakdown: React.FC<PriceBreakdownProps> = ({
  data,
  onProceedToHold,
  canHold = true,
}) => {
  return (
    <div className="price-breakdown-card">
      <div className="breakdown-header">
        <h4 className="breakdown-title">Stay Quote & Breakdown</h4>
        <span className="breakdown-tag">Authoritative Direct Rate</span>
      </div>

      <div className="breakdown-room-info">
        <span className="breakdown-room-name">{data.room_name}</span>
        {data.property_name && <span className="breakdown-property-name">at {data.property_name}</span>}
      </div>

      <div className="breakdown-rows">
        <div className="breakdown-row">
          <span className="row-label">
            Base Stay ({data.nights} {data.nights === 1 ? 'night' : 'nights'} × ₹{data.base_rate_per_night.toLocaleString('en-IN')})
          </span>
          <span className="row-value">₹{data.room_subtotal.toLocaleString('en-IN')}</span>
        </div>

        {data.add_ons && data.add_ons.length > 0 && (
          <div className="breakdown-addons-section">
            <div className="section-label">Selected Add-ons:</div>
            {data.add_ons.map((addon) => (
              <div key={addon.id} className="breakdown-row addon-row">
                <span className="row-label">
                  + {addon.name} <small>({addon.pricing_type.toLowerCase().replace(/_/g, ' ')})</small>
                </span>
                <span className="row-value">
                  ₹{(addon.total ?? addon.price).toLocaleString('en-IN')}
                </span>
              </div>
            ))}
          </div>
        )}

        {data.tax_and_fees !== undefined && data.tax_and_fees > 0 && (
          <div className="breakdown-row tax-row">
            <span className="row-label">Taxes & Service Fees</span>
            <span className="row-value">₹{data.tax_and_fees.toLocaleString('en-IN')}</span>
          </div>
        )}
      </div>

      <div className="breakdown-total-row">
        <span className="total-label">Total Amount</span>
        <span className="total-value">₹{data.total_price.toLocaleString('en-IN')}</span>
      </div>

      {onProceedToHold && (
        <div className="breakdown-actions">
          <button
            type="button"
            className="btn btn-primary btn-full"
            onClick={onProceedToHold}
            disabled={!canHold}
          >
            🔒 Lock in 15-Minute Booking Hold
          </button>
        </div>
      )}
    </div>
  );
};
