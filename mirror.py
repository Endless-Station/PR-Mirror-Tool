import sys
import logging
import config
import os
import subprocess
import tools
import time
from datetime import datetime, timezone
from github import Github


class Mirror:
    def __init__(self):
        self.logger = logging.getLogger("log")
        self.last_activation_day = None
        self.github_api = None
        self.upstream = None
        self.downstream = None

    def initialize(self):
        self.logger.info("Инициализация бота.")
        # Проверяем корректность данных для входа.
        try:
            if config.username and config.password:
                self.github_api = Github(config.username, config.password)
            elif config.api_key:
                self.github_api = Github(config.api_key)
            else:
                self.exit_with_error("Не указано имя пользователя/пароль или API-ключ для GitHub в настройках.")
        except Exception as e:
            self.exit_with_error("Ошибка при входе в GitHub, проверьте правильность данных или попробуйте позже.")

        try:
            self.upstream = self.github_api.get_repo(
                f"{config.upstream_owner}/{config.upstream_repo}")
        except:
            self.exit_with_error("Ошибка при получении информации о исходном репозитории, убедитесь, что указаны правильные имя владельца и название репозитория.")

        try:
            self.downstream = self.github_api.get_repo(
                f"{config.downstream_owner}/{config.downstream_repo}")
        except:
            self.exit_with_error("Ошибка при получении информации о целевом репозитории, убедитесь, что указаны правильные имя владельца и название репозитория.")

        local_dir = config.local_repo_directory

        if not local_dir:
            self.exit_with_error("Папка локального репозитория не настроена в конфигурации.")

        if not config.local_repo_directory:
            self.exit_with_error("Каталог локального репозитория не задан в конфигурации.")

        if os.path.isdir(config.local_repo_directory) and not os.path.isdir(f"{config.local_repo_directory}/.git"):
            self.exit_with_error("Каталог локального репозитория уже существует и не является репозиторием git..")

        if not os.path.isdir(config.local_repo_directory):
            self.logger.warning(
				"Локальный клон потомка не найден, клонирование.")
            try:
                subprocess.check_output(
					["git", "clone", f"https://github.com/{config.downstream_owner}/{config.downstream_repo}", f"{config.local_repo_directory}"])
                current_directory = os.getcwd()
                os.chdir(config.local_repo_directory)
                subprocess.check_output(["git", "remote", "add", "upstream",
                                    f"https://github.com/{config.upstream_owner}/{config.upstream_repo}"])
                subprocess.check_output(["git", "remote", "add", "downstream",
                                    f"https://github.com/{config.downstream_owner}/{config.downstream_repo}"])
                os.chdir(current_directory)
            except:
                self.exit_with_error("Во время клонирования произошла ошибка.")

        if tools.is_gh_installed():
            if not tools.is_gh_logged():
                self.exit_with_error("Авторизация в GitHub CLI не выполнена, выполните авторизацию вручную для продолжения.")
        else:
            self.exit_with_error("GitHub CLI не обнаружена в системе.")

        if config.work_log_file:
            if not os.path.exists(config.work_log_file):
                self.last_activation_day = datetime.now(
                    timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                tools.initialize_work_log(self.last_activation_day)
                self.logger.info("Первичная инициализация рабочего файла.")
            else:
                self.last_activation_day = tools.get_last_activation_day()
                tools.update_activation_day(datetime.now(
                    timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
                self.logger.info(
                    f"Дата последнего включения: {self.last_activation_day}")
                new_prs = []
                if (config.depth_pr_check):
                    new_prs = tools.get_last_merged_prs(f"{config.upstream_owner}/{config.upstream_repo}",
                                                        self.last_activation_day,
                                                        config.depth_pr_check)
                else:
                    self.logger.warn(
                        "Не указана глубина PR для извлечения из репозитория родителя.")
                    new_prs = tools.get_last_merged_prs(f"{config.upstream_owner}/{config.upstream_repo}",
                                                        self.last_activation_day)
                if (new_prs):
                    tools.add_processing_prs(new_prs)
                processing_prs = tools.get_processing_prs()
                if (processing_prs):
                    for pr_number in reversed(processing_prs):
                        mirror_pr(self.upstream, self.downstream, pr_number)
        else:
            self.exit_with_error("В конфигируации отсуствует папка для работы с рабочими логами")
        return

    def run(self):
        self.logger.info("Движок зеркалирования запущен.")
        try:
            for repo, event in github_event_stream(
                self.github_api,
                [self.upstream, self.downstream],
                ["PullRequestEvent", "IssueCommentEvent"]
            ):
                try:
                    if event.type == "PullRequestEvent" and repo == self.upstream:
                        self.logger.debug("Обработка события PR.")
                        if event.payload.get("action") == "closed" and event.payload["pull_request"].get("merged"):
                            self.logger.info("Обработка слияния Pull Request.")
                            
                            pr_number = int(event.payload["pull_request"]["number"])
                            if not tools.check_processed_pr(pr_number):
                                tools.add_processing_pr(pr_number)
                                # Проверка на лимит запросов
                                requests_left, _ = self.github_api.rate_limiting
                                if requests_left < 10:
                                    self.logger.warning("Мало оставшихся запросов к GitHub API. Пропуск зеркалирования.")
                                    continue

                                result = mirror_pr(self.upstream, self.downstream, pr_number)

                                requests_left_after, _ = self.github_api.rate_limiting
                                self.logger.info(
                                    f"Выполнено {requests_left - requests_left_after} запросов ({requests_left_after} осталось)"
                                )
                            else:
                                self.logger.info(f"PR {pr_number} уже был отработан. Пропуск") 
    
                    elif event.type == "IssueCommentEvent" and repo == self.downstream:
                        self.logger.debug("Обработка комментария.")
                        if event.payload.get("action") != "created":
                            continue  # Не удаляем цикл из-за return
                        
                        comment_user = event.payload["comment"]["user"]["login"]
                        comment_body = event.payload["comment"]["body"]
                        action = comment_body.strip().split()[0].lower()
                        self.logger.debug(f"Пользователь: {comment_user}, Действие: {action}")
    
                        if action.startswith("remirror"):
                            association = event.payload["comment"]["author_association"]
                            if association not in ["MEMBER", "OWNER"]:
                                repo.get_comment(event.payload["comment"]["id"]).create_reaction("-1")
                                self.logger.warning("Пользователь не имеет прав на remirror.")
                                continue
                            
                            pr_number = event.payload["issue"]["number"]
                            remirror_pr(self.upstream, self.downstream, pr_number)
    
                except Exception as inner_event_error:
                    self.logger.exception(f"Ошибка при обработке одного из событий GitHub: {inner_event_error}")
    
        except Exception as e:
            self.logger.exception("Ошибка при получении событий из GitHub.")
    
    def exit_with_error(self, message, fatal=True):
        self.logger.critical(message)
        if fatal:
            sys.exit(1)


def clean_repo():
    logger = logging.getLogger("log")
    logger.debug("Cleaning local repo.")
    subprocess.run(["git", "fetch", "--all"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "checkout", "master"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "reset", "--hard", "downstream/master"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "clean", "-f"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.debug("Deleting branches.")
    for deletable_branch in [line.strip().decode() for line in subprocess.check_output(["git", "branch"]).splitlines() if line != b"* master"]:
        subprocess.run(["git", "branch", "-D", deletable_branch],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mirror_pr(upstream, downstream, pr_id):
    logger = logging.getLogger("log")
    logger.info(f"Зеркалирование PR #{pr_id}.")
    current_directory = os.getcwd()
    try:
        os.chdir(config.local_repo_directory)
        original_pull = upstream.get_pull(pr_id)
        clean_repo()
        subprocess.run(["git", "checkout", "-b", f"{config.mirror_branch_prefix}{pr_id}"],
                       )
        try:
            cherry_out = subprocess.check_output(["git", "cherry-pick", "-m", "1",
                                                  original_pull.merge_commit_sha], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            cherry_out = str(e.output)

        try:
            cherry_out = cherry_out.decode()  # love python3
        except:
            pass

        if "mainline was specified but commit" in cherry_out:
            commits = original_pull.get_commits()
            subprocess.run(["git", "fetch", "--all"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if original_pull.merge_commit_sha in [c.sha for c in commits]:
                for c in commits:
                    subprocess.run(
                        ["git", "cherry-pick", "--no-commit", "-n", c.sha])
                    subprocess.run(["git", "add", "-A", "."])
                    subprocess.run(
                        ["git", "commit", "--no-edit", "-m", c.commit.message])
                    subprocess.run(["git", "cherry-pick", "--continue"])
            else:
                subprocess.run(["git", "cherry-pick", "--no-commit", "-n",
                                original_pull.merge_commit_sha])
                subprocess.run(["git", "add", "-A", "."])
                subprocess.run(["git", "commit", "--no-edit",
                               "-m", original_pull.title])
                subprocess.run(["git", "cherry-pick", "--continue"])
        else:
            subprocess.run(["git", "add", "-A", "."])

        subprocess.run(["git", "commit", "--allow-empty", "--no-edit", "-m", original_pull.title],
                       )
        subprocess.run(["git", "push", "downstream",
                        f"{config.mirror_branch_prefix}{pr_id}"], )

        pr_body = original_pull.body if original_pull.body != None else ""
        result = downstream.create_pull(title=f"{config.mirror_pr_title_prefix}{original_pull.title} [MDB IGNORE]",
                                        body=f"Original PR: {pr_id}\n-----\n{pr_body.replace('@', '')}",
                                        base="master",
                                        head=f"{config.mirror_branch_prefix}{pr_id}",
                                        maintainer_can_modify=True)

        logger.info(f"PR создан: {result.title} (#{result.number})")
        os.chdir(current_directory)
        tools.add_processed_pr(pr_id)
        return result
    except:
        logger.exception(
            f"Во время зеркалирования PR #{pr_id} произошла ошибка.")
    finally:
        os.chdir(current_directory)


def remirror_pr(upstream, downstream, mirror_pr_id):
    logger = logging.getLogger("log")
    logger.info(f"Remirroring #{mirror_pr_id}.")
    current_directory = os.getcwd()
    try:
        os.chdir(config.local_repo_directory)
        mirror_pull = downstream.get_pull(mirror_pr_id)
        # Get original PR number from the "Original PR: " link
        original_pull = upstream.get_pull(
            int(mirror_pull.body.split("/")[6].split("\n")[0]))
        clean_repo()
        logger.debug("Switching to mirror branch.")
        subprocess.run(["git", "checkout", "-b", f"{config.mirror_branch_prefix}{original_pull.number}"],
                       )
        logger.debug("Cherry-picking merge commit.")
        subprocess.run(["git", "cherry-pick", "-m", "1", original_pull.merge_commit_sha],
                       )
        logger.debug("Force pushing to downstream.")
        subprocess.run(["git", "push", "--force", "downstream",
                        f"{config.mirror_branch_prefix}{original_pull.number}"], )
    except:
        logger.exception("An error occured during remirroring.")
    finally:
        os.chdir(current_directory)


def github_event_stream(github_api, repos, req_types):
    logger = logging.getLogger("log")
    last_seen_ids = {}
    for repo in repos:
        last_seen_ids[repo.html_url] = int(repo.get_events()[0].id)
    logger.info("Запуск потока событий.")
    for i in range(60):
        requests_left, request_limit = github_api.rate_limiting
        for repo in repos:
            event_list = []
            try:
                for e in repo.get_events():
                    event_list.append(e)
            except:
                logger.exception("Произошла ошибка при получении событий.")
                continue
            event_list = [e for e in event_list if int(
                e.id) > last_seen_ids[repo.html_url]]
            event_list.sort(key=lambda e: int(e.id))
            if not event_list:
                logger.debug("Нет новых событий.")  # "No new events."
            for e in event_list:
                if e.type in req_types:
                    logger.debug("Передача события.")  # "Yielding event."
                    yield repo, e
                last_seen_ids[repo.html_url] = int(e.id)
        requests_left_after, request_limit_after = github_api.rate_limiting
        logger.info(f"Иттерация: {i} Выполнено {requests_left - requests_left_after} запросов ({requests_left_after} осталось)")
        logger.debug(f"Проверка через {config.event_stream_wait} секунд.")
        time.sleep(config.event_stream_wait)
