import { PublicCard, PublicPage } from "@/components/public-page";

const methods = [
  {
    title: "Банковская карта",
    text: "Оплата тарифа через защищенный эквайринг после подключения платежного провайдера.",
  },
  {
    title: "Электронные платежи",
    text: "Возможность подключить удобный платежный сценарий для физических лиц и небольших команд.",
  },
  {
    title: "Счет для юрлиц",
    text: "Безналичная оплата с закрывающими документами и ручным подтверждением администратором.",
  },
];

export default function PaymentPage() {
  return (
    <PublicPage
      eyebrow="Оплата"
      title="Способы оплаты сервиса"
      description="Платежный модуль рассчитан на тарифы, счета, историю оплат и автоматическую выдачу доступа после успешной оплаты."
    >
      <section className="public-card-grid">
        {methods.map((item) => (
          <PublicCard key={item.title} title={item.title} text={item.text} />
        ))}
      </section>
    </PublicPage>
  );
}
