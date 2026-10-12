import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Individual loan and servicing practice | InvestOffice",
  description: "Practice an individual rental-property application, review, and payment ledger with fictional information.",
};

export default function IndividualLayout({ children }: { children: React.ReactNode }) {
  return children;
}
