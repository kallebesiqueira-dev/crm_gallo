import {
  CalendarDays,
  Circle,
  FileSignature,
  FileText,
  Mail,
  MessageCircle,
  Phone,
  RefreshCw,
  Zap,
  type LucideIcon,
} from "lucide-react";

// Lucide icon per deal next-action type — replaces the emoji map that was
// duplicated across the pipeline board, deal detail and the Hoje screen.
// Stroke is currentColor, so the icon inherits the surrounding text colour
// (e.g. red when the follow-up is overdue).
const ICONS: Record<string, LucideIcon> = {
  call: Phone,
  whatsapp: MessageCircle,
  email: Mail,
  proposal: FileText,
  meeting: CalendarDays,
  follow_up: RefreshCw,
  contract: FileSignature,
  chase: Zap,
  other: Circle,
};

export function ActionIcon({
  type,
  className = "h-4 w-4",
}: {
  type?: string | null;
  className?: string;
}) {
  const Icon = (type && ICONS[type]) || Circle;
  return <Icon className={className} aria-hidden />;
}
