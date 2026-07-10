import {
  Beef, Drumstick, Salad, Utensils, Snowflake, Milk, Fish, Wheat, Factory,
  Coffee, CupSoda, Sprout, Leaf, ShoppingBasket,
  Flag, Globe, Target, Package, Box, Lightbulb, Store, Truck,
  Calendar, CalendarDays, MapPin, Clock, Star, ChevronRight, CircleChevronRight,
} from "lucide-react";
import type { ComponentType } from "react";

/**
 * Lucide icon resolver (https://lucide.dev/icons). Content stores a kebab-case
 * Lucide name in an icon/iconClass field; views render <LucideIcon name={...} />.
 * Brand/social icons stay on Font Awesome (Lucide has no brand logos).
 * Curated map — add the icon's export here when a new name is used in content.
 */
type IconProps = { size?: number | string; className?: string; strokeWidth?: number; "aria-hidden"?: boolean };

const MAP: Record<string, ComponentType<IconProps>> = {
  beef: Beef, drumstick: Drumstick, salad: Salad, utensils: Utensils, snowflake: Snowflake,
  milk: Milk, fish: Fish, wheat: Wheat, factory: Factory, coffee: Coffee, "cup-soda": CupSoda,
  sprout: Sprout, leaf: Leaf, "shopping-basket": ShoppingBasket,
  flag: Flag, globe: Globe, target: Target, package: Package, box: Box, lightbulb: Lightbulb,
  store: Store, truck: Truck,
  calendar: Calendar, "calendar-days": CalendarDays, "map-pin": MapPin, clock: Clock,
  star: Star, "chevron-right": ChevronRight, "circle-chevron-right": CircleChevronRight,
};

export function LucideIcon({
  name,
  size = 24,
  className,
  strokeWidth = 2,
}: {
  name?: string;
  size?: number;
  className?: string;
  strokeWidth?: number;
}) {
  if (!name) return null;
  const Cmp = MAP[name.trim().toLowerCase()];
  if (!Cmp) return null;
  return <Cmp size={size} className={className} strokeWidth={strokeWidth} aria-hidden={true} />;
}
