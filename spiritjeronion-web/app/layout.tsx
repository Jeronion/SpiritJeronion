import type { Metadata } from 'next';
import { Manrope } from 'next/font/google';
import './globals.css';

const manrope = Manrope({ variable: '--font-manrope', subsets: ['cyrillic', 'latin'] });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'),
  title: 'SpiritJeronion — школьный ассистент',
  description: 'Личный кабинет с расписанием, новостями, домашними заданиями и учебниками.',
  openGraph: {
    title: 'SpiritJeronion',
    description: 'Твой школьный день — в одном месте',
    images: ['/og.png'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'SpiritJeronion',
    description: 'Твой школьный день — в одном месте',
    images: ['/og.png'],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body className={manrope.variable}>{children}</body></html>;
}
