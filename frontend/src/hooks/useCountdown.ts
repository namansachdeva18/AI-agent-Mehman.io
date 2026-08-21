import { useEffect, useState } from 'react';

export interface CountdownResult {
  formatted: string;
  isExpired: boolean;
  secondsRemaining: number;
}

export function useCountdown(targetIsoDate: string | null | undefined, onExpire?: () => void): CountdownResult {
  const [secondsRemaining, setSecondsRemaining] = useState<number>(() => {
    if (!targetIsoDate) return 0;
    const diff = Math.floor((new Date(targetIsoDate).getTime() - Date.now()) / 1000);
    return Math.max(0, diff);
  });

  useEffect(() => {
    if (!targetIsoDate) {
      setSecondsRemaining(0);
      return;
    }

    const updateTimer = () => {
      const diff = Math.floor((new Date(targetIsoDate).getTime() - Date.now()) / 1000);
      const rem = Math.max(0, diff);
      setSecondsRemaining(rem);
      if (rem === 0 && onExpire) {
        onExpire();
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [targetIsoDate, onExpire]);

  const minutes = Math.floor(secondsRemaining / 60);
  const seconds = secondsRemaining % 60;
  const formatted = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

  return {
    formatted,
    isExpired: targetIsoDate ? secondsRemaining <= 0 : false,
    secondsRemaining,
  };
}
