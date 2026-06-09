import Link from "next/link";
import { PublicPage, PublicSection } from "@/components/public-page";

export default function RecoveryPage() {
  return (
    <PublicPage
      eyebrow="Доступ"
      title="Восстановление аккаунта"
      description="В текущей версии восстановление пароля выполняется через администратора платформы, чтобы не оставлять пользователя без доступа к рабочим задачам."
    >
      <PublicSection title="Как восстановить доступ">
        <p>
          Напишите администратору проекта email аккаунта. После проверки администратор сможет обновить доступ
          или выдать временный пароль через панель управления.
        </p>
        <p>
          Если у вас есть действующий пароль, вернитесь на страницу входа и продолжите работу с задачами.
        </p>
        <Link className="primary-button" href="/login">
          Вернуться ко входу
        </Link>
      </PublicSection>
    </PublicPage>
  );
}
