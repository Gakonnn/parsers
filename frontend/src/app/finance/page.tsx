import Link from "next/link";
import { PublicPage } from "@/components/public-page";

const plans = [
  { name: "Бесплатный", price: "0 ₸", runs: "3 запуска", records: "50 записей", note: "Для тестирования кабинета" },
  { name: "Старт", price: "4 000 ₸", runs: "10 запусков", records: "500 записей", note: "Для небольших регулярных задач" },
  { name: "Мини-бизнес", price: "10 000 ₸", runs: "25 запусков", records: "2 000 записей", note: "Для активного сбора данных" },
  { name: "Бизнес", price: "25 000 ₸", runs: "70 запусков", records: "10 000 записей", note: "Для отдела продаж или аналитики" },
  { name: "Профи", price: "50 000 ₸", runs: "180 запусков", records: "35 000 записей", note: "Для высокой нагрузки" },
  { name: "Enterprise", price: "100 000 ₸", runs: "500 запусков", records: "100 000 записей", note: "Для команд и кастомных условий" },
];

export default function FinancePage() {
  return (
    <PublicPage
      eyebrow="Тарифы"
      title="Планы под разные объемы данных"
      description="Тарифы можно ограничивать по количеству запусков, записей, доступным источникам и сроку действия подписки."
    >
      <section className="public-pricing-grid">
        {plans.map((plan) => (
          <article className="public-plan-card" key={plan.name}>
            <span className="soft-badge">{plan.name}</span>
            <strong>{plan.price}</strong>
            <p>{plan.note}</p>
            <ul>
              <li>{plan.runs}</li>
              <li>{plan.records}</li>
              <li>CSV и Excel экспорт</li>
            </ul>
            <Link className="primary-button wide" href="/">
              Выбрать тариф
            </Link>
          </article>
        ))}
      </section>
    </PublicPage>
  );
}
