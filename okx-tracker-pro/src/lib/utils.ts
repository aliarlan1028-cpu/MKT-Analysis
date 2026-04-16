import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatPrice(price: number): string {
  if (price === 0) return '0.00';
  
  const absPrice = Math.abs(price);
  if (absPrice >= 1000) {
    return price.toFixed(2);
  } else if (absPrice >= 1) {
    return price.toFixed(4);
  } else if (absPrice >= 0.01) {
    return price.toFixed(6);
  } else {
    return price.toFixed(8);
  }
}

export function formatPercent(value: number): string {
  return (value >= 0 ? '+' : '') + value.toFixed(2) + '%';
}
