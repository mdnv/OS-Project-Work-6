# Пошаговая инструкция: MacBook → Ubuntu через SSH → GitHub

Все программы выполняются в Ubuntu. Mac используется для терминала,
скачивания архива и браузера. Проект не требует pip или venv.

## 1. Подготовить Ubuntu

В уже открытой SSH-сессии:

```bash
whoami
uname -s
python3 --version
```

Ожидается имя вашего пользователя, `Linux` и версия Python 3.
Если `uname -s` показал `Darwin`, это локальный терминал Mac: подключитесь
к Ubuntu привычной командой SSH.

Установите необходимые программы:

```bash
sudo apt update
sudo apt install -y python3 git unzip gh
```

Пароль sudo — пароль пользователя Ubuntu. Символы при вводе не видны.

## 2. Перенести проект

Скачайте выданный архив `OS-Project-Work-6.zip` в Downloads на Mac.
Не распаковывайте его до переноса, если будете использовать команду scp ниже.

В Терминале Mac нажмите Command+T. Новая вкладка должна быть локальной.
Проверьте:

```bash
uname -s
ls ~/Downloads/OS-Project-Work-6.zip
```

Ожидается `Darwin` и путь к архиву. Перенос для подключения по IP:

```bash
scp ~/Downloads/OS-Project-Work-6.zip USER@IP:~/
```

Замените USER и IP на те же значения, что используете в своём SSH-подключении.
Например, при `ssh student@192.168.1.50` используйте
`scp ~/Downloads/OS-Project-Work-6.zip student@192.168.1.50:~/`.
Это пример, а не адрес вашей машины.

Если ваше подключение использует порт 2222 и адрес 127.0.0.1:

```bash
scp -P 2222 ~/Downloads/OS-Project-Work-6.zip USER@127.0.0.1:~/
```

У SSH порт задаётся `-p`, у scp — `-P`. При нестандартном ключе повторите
также параметр `-i` из своего SSH-подключения.
В scp используется адрес существующего подключения, а не новый адрес,
подсмотренный внутри виртуальной машины.

Если Safari уже распаковал архив, перенесите папку:

```bash
scp -r ~/Downloads/OS-Project-Work-6 USER@IP:~/
```

В этом случае распаковку в следующем шаге пропустите.

## 3. Открыть проект в Ubuntu

Вернитесь в SSH-вкладку. Если папка с таким названием уже существует,
сначала сохраните её под другим именем: не перезаписывайте свои изменения.
Для первого переноса:

```bash
unzip ~/OS-Project-Work-6.zip -d ~
cd ~/OS-Project-Work-6
pwd
ls -a
mkdir -p results
```

Ожидается путь `/home/ВАШ_ПОЛЬЗОВАТЕЛЬ/OS-Project-Work-6` и шесть файлов
Python, README.md, INSTRUCTIONS.md, .gitignore. Код можно посмотреть:

```bash
less pc_fixed.py
```

Для выхода из less нажмите q. Для редактирования:

```bash
nano pc_fixed.py
```

Сохранение: Control+O, Enter; выход: Control+X. Именно Control, не Command.

## 4. Показать гонку и её исправление

Чтобы сохранять вывод и корректно получать код ошибки программы через tee:

```bash
set -o pipefail
python3 race.py | tee results/race.txt
python3 race_fixed.py | tee results/race_fixed.txt
```

Сломанная версия: Expected=4000, Actual=1000, Lost=3000,
RACE DETECTED. Исправленная: Expected=4000, Actual=4000,
PASS: counter invariant. Ошибка первой версии ожидаема и записана в лог.

Барьер в race.py только задаёт последовательность чтений и записей;
операцию изменения он не защищает. Сравните оба файла:

```bash
diff -u race.py race_fixed.py
```

У diff код возврата 1 означает найденные различия — это нормально.

## 5. Буфер с семафорами

```bash
python3 pc_fixed.py --mode sem | tee results/pc_sem.txt
```

Ожидается строка:

```text
PASS mode=sem run=1 produced=1000 consumed=1000 unique=1000 max_buffer=5/5 final_buffer=0 violations=0
```

max_buffer может оказаться меньше 5. Правильный диапазон — 1..5.
В pc_fixed.py найдите класс SemaphoreBuffer: `empty=5`, `full=0`, Lock.
Ожидание семафора выполняется до захвата мьютекса.

## 6. Буфер с Condition

```bash
python3 pc_fixed.py --mode cond | tee results/pc_cond.txt
```

Ожидается аналогичная строка с mode=cond и violations=0.
Найдите класс ConditionBuffer. В put — `while count == CAPACITY`,
в get — `while count == 0`. Condition использует явно созданный Lock.
Обработка и искусственные задержки находятся вне блокировки буфера.

Проверка буфера в RingBuffer.check и проверка Counter в run_once
подтверждают корректность кодом. Одного числа consumed=1000 было бы
недостаточно: при нём могли бы скрываться дубли и пропущенные ID.

## 7. Повторные проверки

```bash
python3 pc_fixed.py --mode sem --runs 20 | tee results/stress_sem.txt
python3 pc_fixed.py --mode cond --runs 20 | tee results/stress_cond.txt
```

Ожидается по 20 строк PASS, run от 1 до 20, violations=0 в каждой.
Каждый повтор обрабатывает новый набор из 1000 ID, а не делит 1000 на 20.
Повторы увеличивают шанс обнаружить ошибку, но сами по себе не доказывают
корректность при всех возможных чередованиях: нужны также инварианты.

## 8. Барьер

```bash
python3 barrier.py | tee results/barrier.txt
```

Ожидается 12 строк T1..T4: phase 1..3 done и в конце:

```text
PASS: 4 threads, 3 phases, violations=0
```

Порядок T1..T4 внутри фазы может меняться. Все четыре строки фазы 1
должны появиться до первой строки фазы 2, затем все четыре фазы 2 —
до фазы 3. Кроме вывода, это контролируется проверками внутри программы.
Смотрите ReusableBarrier: счётчик arrived и номер generation.

## 9. Ошибка if вместо while

```bash
python3 condition_if_bug.py --mode if | tee results/condition_if.txt
python3 condition_if_bug.py --mode while | tee results/condition_while.txt
```

Первый результат:

```text
mode=if consumed=1 violations=1
EXPECTED BUG: empty buffer after wait
```

Второй результат:

```text
mode=while consumed=1 violations=0
PASS: condition checked again
```

Пример специально маленький: два потребителя и один элемент в кольце
на 5 ячеек. Основное условие 3/2/1000 проверяется отдельно в pc_fixed.py.
Оба потребителя ждут, producer добавляет один элемент и будит обоих,
первый забирает элемент, второй продолжает после wait. С if он не
проверяет пустоту вновь; с while ждёт повторно. В исправленной демонстрации
закрытие буфера позволяет второму потребителю завершиться без зависания.

Не нужно портить основную исправленную программу заменой while на if:
ошибка уже изолирована в отдельном приложенном файле.

## 10. Настоящее потерянное уведомление

```bash
python3 lost_wakeup.py | tee results/lost_wakeup.txt
python3 lost_wakeup.py --fixed | tee results/lost_wakeup_fixed.txt
```

Ожидается соответственно:

```text
EXPECTED BUG: ready=True, wait timed out
PASS: predicate true, no wait needed
```

В сломанном примере потребитель проверил условие и отпустил мьютекс,
producer выставил ready=True и вызвал notify, а consumer только потом
вызвал wait. Уведомление уже прошло; ожидание завершается по тайм-ауту.
Это отдельный сбой, отличающийся от отсутствия перепроверки после пробуждения.

## 11. Проверить логи

```bash
ls logs
cat logs/race.log
cat logs/condition_if.log
cat logs/lost_wakeup_bug.log
rg 'ERROR|FAILED' logs/pc_sem.log logs/pc_cond.log logs/barrier.log
```

Если rg не установлен, используйте:

```bash
grep -nE 'ERROR|FAILED' logs/pc_sem.log logs/pc_cond.log logs/barrier.log
```

В исправленных программах совпадений быть не должно. Пустой вывод и
код возврата 1 у rg/grep означают отсутствие совпадений, а не сбой программы.
Логи гонки, if и потерянного уведомления специально содержат ERROR.

## 12. GitHub

В браузере Mac откройте https://github.com/new.
Назовите репозиторий OS-Project-Work-6, выберите Public либо Private по
требованию преподавателя. Не добавляйте README, .gitignore или license
при создании: они уже есть локально. Нажмите Create repository.

В SSH-вкладке Ubuntu:

```bash
cd ~/OS-Project-Work-6
git init -b main
git config user.name "ВАШЕ ИМЯ"
git config user.email "ВАШ EMAIL ДЛЯ GIT"
gh auth login --hostname github.com --git-protocol https --web
```

Вместо двух строк-заглушек укажите свои данные. Можно использовать
noreply-адрес из настроек GitHub → Emails.

Если CLI спрашивает об аутентификации Git, выберите Yes.
Скопируйте одноразовый код, который вывела именно команда gh. Если она
предлагает нажать Enter, нажмите. В браузере Mac откройте
https://github.com/login/device, войдите в нужную учётную запись,
введите показанный код и подтвердите Authorize GitHub CLI.
Если Ubuntu не может открыть браузер — это нормально: браузер нужен на Mac.
Не используйте для этого поля код из приложения «Пароли»: CLI показывает
свой отдельный код авторизации устройства. Если сам GitHub отдельно
запросит 2FA при входе, это другое поле.

Вернитесь в Ubuntu и выполните:

```bash
gh auth status
gh auth setup-git
git add .gitignore README.md INSTRUCTIONS.md *.py results/ logs/
git status
git commit -m "Add synchronization lab 6 variant B"
```

Добавьте HTTPS-адрес репозитория, скопированный с GitHub. Пример
с обязательной заменой YOUR_LOGIN на свой логин:

```bash
git remote add origin https://github.com/YOUR_LOGIN/OS-Project-Work-6.git
git push -u origin main
```

Ожидается отправка объектов, новая ветка main и сообщение об отслеживании
origin/main. Откройте репозиторий в браузере и обновите страницу:
должны быть файлы кода, README, инструкции, results и logs.
Пароли, SSH-ключи и файлы авторизации gh находятся вне проекта и в commit
не включаются. Секреты нельзя вставлять в код или README.

Для последующих изменений:

```bash
git add .gitignore README.md INSTRUCTIONS.md *.py results/ logs/
git commit -m "Update synchronization lab"
git push
```

## Если результат отличается

| Ситуация | Действие |
|---|---|
| uname показывает Darwin | Подключитесь по SSH, запускать надо в Ubuntu |
| python3: command not found | `sudo apt install -y python3` |
| gh: command not found | `sudo apt install -y gh` |
| apt: Could not get lock | Дождитесь завершения другого apt/обновления и повторите; lock-файлы не удаляйте |
| scp: No such file | `ls ~/Downloads`, уточните имя скачанного файла; путь с пробелами заключите в кавычки |
| Connection refused у scp | Проверьте запуск VM, адрес и порт существующего SSH; используйте -P для порта |
| can't open file | `cd ~/OS-Project-Work-6`, затем `ls` |
| ModuleNotFoundError: pc_fixed | Держите condition_if_bug.py и pc_fixed.py в одной папке |
| max_buffer меньше 5 | Это допустимо: превышения 5 быть не должно |
| ERROR в condition_if.log | Ожидаемый специально вызванный сбой |
| Тайм-аут или зависание | Control+C; прочитайте соответствующий logs/*.log; сравните код с исходным архивом |
| Что-то изменили и появилась ошибка | `git diff`; исправьте только изменённые места, не удаляйте проект |
| remote origin already exists | `git remote -v`; при неверном URL `git remote set-url origin https://github.com/YOUR_LOGIN/OS-Project-Work-6.git` |
| Author identity unknown | Выполните git config user.name и git config user.email в проекте |
| Authentication failed | `gh auth status`, повторите gh auth login и gh auth setup-git |
| Repository not found | Проверьте логин, имя репозитория, учётную запись gh auth status и права доступа |
| non-fast-forward | `git fetch origin`, `git log --oneline --graph --all`; если в удалённом репозитории только автоматически созданный README — `git pull --no-rebase origin main --allow-unrelated-histories`, разрешите конфликты, затем commit и push |
| GH013 / secret scanning | Не обходите блокировку: удалите секрет из файлов и затронутых коммитов, отзовите его; простого нового коммита с удалением недостаточно |
| Нужно отправить изменённый файл на Mac | Из локальной вкладки: `scp USER@IP:~/OS-Project-Work-6/pc_fixed.py ~/Downloads/` |

## Что приложить и рассказать

Отправьте ссылку на GitHub. Сохраните исходники обеих версий счётчика,
оба варианта буфера, барьер, демонстрации if и потерянного уведомления,
README, собственные результаты и логи.

На защите покажите чтение/запись под Lock, роли empty/full, цикл while
вокруг wait, смену поколения барьера и проверки Counter/кольца.
Ответы на контрольные вопросы и объяснение чередований есть в README.
До выполнения собственных запусков не представляйте таблицу ожидаемых
результатов как личные измерения.
