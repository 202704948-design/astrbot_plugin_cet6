import os
import json
import random
import time
import asyncio
import shutil 
from datetime import datetime
from astrbot.api.all import *
from astrbot.api.event import filter
from astrbot.api import logger
from astrbot.api.message_components import Plain 

# ==========================================
# ⚙️ 配置文件与存储路径
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
USER_VOCAB_PATH = os.path.join(BASE_DIR, 'user_vocab.json') 
SUBSCRIBER_PATH = os.path.join(BASE_DIR, 'subscribers.json') 
MASTERED_VOCAB_PATH = os.path.join(BASE_DIR, 'mastered_vocab.json') 
DONE_READINGS_PATH = os.path.join(BASE_DIR, 'done_readings.json') 

DEFAULT_CONFIG = {
    "command_draw_reading": "来篇阅读",
    "command_submit_answer": "答案",
    "command_check_answer": "查答案", 
    "command_random_vocab": "抽单词",
    "command_search_vocab": "查单词",
    "command_add_vocab": "加生词",
    "command_review_vocab": "今日复习",
    "command_forget_vocab": "忘",       
    "command_get_new": "今日新词",
    "command_my_stats": "我的词库",    
    "command_set_alarm": "复习提醒",
    "command_help": "使用文档"         
}

if not os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f: json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
        cfg = DEFAULT_CONFIG
    except Exception: cfg = DEFAULT_CONFIG
else:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f: 
            cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg: cfg[k] = v
    except Exception: cfg = DEFAULT_CONFIG

EBBINGHAUS_INTERVALS = [43200, 86400, 172800, 345600, 604800, 1296000]
RANKS = ['待定 🥚', '模糊 📉', '清晰 📈', '记住 🧠', '牢固 🛡️', '掌握 🌟', '精通 👑']

# ==========================================
# 🤖 插件核心逻辑
# ==========================================
@register("cet6_tutor", "YourName", "四六级金牌私教", "5.1.0")
class CET6Tutor(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}  
        
        self.questions = []
        self.answers = {}
        self.user_sessions = {}       
        self.vocab_random_list = []
        self.vocab_fast_dict = {}     
        self.user_vocab_db = {} 
        self.subscribers = {} 
        self.mastered_vocab_db = {} 
        self.done_readings_db = {} 
        
        self.load_data()
        asyncio.create_task(self.daily_push_task())

    # ==========================================
    # 📚 动态使用文档 (帮助菜单 + 倒计时)
    # ==========================================
    @filter.command(cfg.get("command_help", "使用文档"))
    async def show_help(self, event: AstrMessageEvent):
        # 🌟 智能倒计时逻辑
        today = datetime.now().date()
        year = today.year
        exam_june = datetime(year, 6, 13).date()
        exam_dec = datetime(year, 12, 13).date()
        
        if today > exam_dec:
            next_exam = datetime(year + 1, 6, 13).date()
        elif today > exam_june:
            next_exam = exam_dec
        else:
            next_exam = exam_june
            
        days_left = (next_exam - today).days

        reply = "🎓 【 四六级金牌私教 - 终极使用指南 】 🎓\n"
        reply += "=" * 28 + "\n"
        reply += "📖 沉浸式阅读模块 (已开启防重复机制)\n"
        reply += f" ▫️ /{cfg.get('command_draw_reading', '来篇阅读')} : 抽取未做过的阅读\n"
        reply += f" ▫️ /{cfg.get('command_submit_answer', '答案')} ABCD : 提交选项并出分\n"
        reply += f" ▫️ /{cfg.get('command_check_answer', '查答案')} : 放弃做题，直接看答案\n\n"
        reply += "🔥 单词核武器模块\n"
        reply += f" ▫️ /{cfg.get('command_search_vocab', '查单词')} word : 查详细释义\n"
        reply += f" ▫️ /{cfg.get('command_random_vocab', '抽单词')} : 随机抽取5词闪测\n"
        reply += f" ▫️ /{cfg.get('command_get_new', '今日新词')} 35 : 批量拉取新词入库\n"
        reply += f" ▫️ /{cfg.get('command_add_vocab', '加生词')} word : 手动捕捉生词入库\n\n"
        reply += "🧠 艾宾浩斯记忆引擎\n"
        reply += f" ▫️ /{cfg.get('command_review_vocab', '今日复习')} : 获取今日到期复习任务\n"
        reply += f" ▫️ /{cfg.get('command_forget_vocab', '忘')} word : 没记住？一键惩罚降级\n"
        reply += f" ▫️ /{cfg.get('command_my_stats', '我的词库')} : 查看词库与刷题战绩\n"
        reply += f" ▫️ /{cfg.get('command_set_alarm', '复习提醒')} 08:30 : 开启每日自动推送\n"
        reply += "=" * 28 + "\n"
        # 🌟 渲染压迫感极强的倒计时
        reply += f"⏳ 距离下一次大考 ({next_exam.year}年{next_exam.month}月) 仅剩：{days_left} 天！\n"
        reply += "💡 战友，时不我待，立刻拔剑吧！"
        
        yield event.plain_result(reply)

    def get_human_time(self, timestamp):
        target = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        days_diff = (target.date() - now.date()).days
        if days_diff < 0: return "已逾期 🔥"
        elif days_diff == 0: return "今晚" if target.hour >= 12 else "今天"
        elif days_diff == 1: return "明晚" if target.hour >= 12 else "明早"
        elif days_diff == 2: return "后天"
        else: return f"{days_diff}天后"

    async def daily_push_task(self):
        logger.info("[CET6 Tutor] ⏱️ 定时推送巡逻任务已启动！")
        while True:
            try:
                now_time_str = datetime.now().strftime("%H:%M")
                for user_id, sub_info in self.subscribers.items():
                    if sub_info.get("time") == now_time_str and not sub_info.get("notified_today"):
                        reply = self.generate_review_report(user_id)
                        notify_text = f"🔔 【叮咚！复习时间到】\n{reply}" if reply else "🔔 【叮咚！复习时间到】\n🎉 太棒了！今天你的记忆曲线很完美，没有需要复习的生词！"
                        await self.context.send_message(sub_info["platform"], sub_info["session_id"], [Plain(notify_text)])
                        sub_info["notified_today"] = True
                        self.save_subscribers()
                if now_time_str == "00:00":
                    for sub_info in self.subscribers.values(): sub_info["notified_today"] = False
                    self.save_subscribers()
            except Exception as e:
                logger.error(f"[CET6 Tutor] 定时推送报错: {e}")
            await asyncio.sleep(60) 

    def load_data(self):
        q_path = os.path.join(BASE_DIR, 'CET6_Perfect_Verified.json')
        a_path = os.path.join(BASE_DIR, 'CET6_Answer.json')
        txt_path = os.path.join(BASE_DIR, '4 六级-乱序.txt')
        json_path = os.path.join(BASE_DIR, '4-CET6-顺序.json')
        
        try:
            with open(q_path, 'r', encoding='utf-8') as f: self.questions = json.load(f)
            with open(a_path, 'r', encoding='utf-8') as f: self.answers = json.load(f)
        except Exception: pass

        try:
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f: self.vocab_random_list = [line.strip().split()[0] for line in f if line.strip()]
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    raw_vocab = json.load(f)
                if isinstance(raw_vocab, dict):
                    for k, v in raw_vocab.items(): self.vocab_fast_dict[k.lower()] = json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, (dict, list)) else str(v)
                elif isinstance(raw_vocab, list):
                    for item in raw_vocab:
                        if isinstance(item, dict):
                            for val in item.values():
                                val_str = str(val).lower().strip()
                                if val_str.isalpha(): self.vocab_fast_dict[val_str] = json.dumps(item, ensure_ascii=False, indent=2)
        except Exception: pass

        if os.path.exists(USER_VOCAB_PATH):
            try:
                with open(USER_VOCAB_PATH, 'r', encoding='utf-8') as f: self.user_vocab_db = json.load(f)
            except Exception: pass
            
        if os.path.exists(SUBSCRIBER_PATH):
            try:
                with open(SUBSCRIBER_PATH, 'r', encoding='utf-8') as f: self.subscribers = json.load(f)
            except Exception: pass

        if os.path.exists(MASTERED_VOCAB_PATH):
            try:
                with open(MASTERED_VOCAB_PATH, 'r', encoding='utf-8') as f: self.mastered_vocab_db = json.load(f)
            except Exception: pass
            
        if os.path.exists(DONE_READINGS_PATH):
            try:
                with open(DONE_READINGS_PATH, 'r', encoding='utf-8') as f: self.done_readings_db = json.load(f)
            except Exception: pass

    def safe_save(self, path, data):
        try:
            if os.path.exists(path): shutil.copyfile(path, path + ".bak")
            with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e: logger.error(f"[CET6 Tutor] 保存 {path} 失败：{e}")

    def save_user_vocab(self): self.safe_save(USER_VOCAB_PATH, self.user_vocab_db)
    def save_mastered_vocab(self): self.safe_save(MASTERED_VOCAB_PATH, self.mastered_vocab_db)
    def save_subscribers(self): self.safe_save(SUBSCRIBER_PATH, self.subscribers)
    def save_done_readings(self): self.safe_save(DONE_READINGS_PATH, self.done_readings_db) 

    def cleanup_sessions(self):
        now = time.time()
        expired_users = [uid for uid, data in self.user_sessions.items() if now - data["time"] > 7200]
        for uid in expired_users: del self.user_sessions[uid]

    def get_q_id(self, meta, sec_type):
        return f"{meta.get('year')}_{meta.get('month')}_{meta.get('set_index')}_{sec_type}"

    def get_answer_key(self, meta, sec_type):
        year = str(meta.get('year', '')).strip()
        month = str(meta.get('month', '')).strip().zfill(2)
        set_idx = str(meta.get('set_index', '1')).strip()

        target_id = f"{year}_{month}_{set_idx}"
        ans_dict = self.answers.get(target_id, {}).get("answers", {})

        if not ans_dict: return None

        sec_type_up = sec_type.upper()
        raw_ans, expected_len = "", 0

        if "A" in sec_type_up and "B" not in sec_type_up and "C" not in sec_type_up:
            raw_ans, expected_len = ans_dict.get("Section A", ""), 10
        elif "B" in sec_type_up:
            raw_ans, expected_len = ans_dict.get("Section B", ""), 10
        elif "C" in sec_type_up:
            if "1" in sec_type_up or "ONE" in sec_type_up:
                raw_ans, expected_len = ans_dict.get("Section C1", ""), 5
            elif "2" in sec_type_up or "TWO" in sec_type_up:
                raw_ans, expected_len = ans_dict.get("Section C2", ""), 5
            else:
                c1 = ans_dict.get("Section C1", "")
                c2 = ans_dict.get("Section C2", "")
                if c1 and c2: raw_ans, expected_len = c1 + c2, 10
                else: raw_ans, expected_len = ans_dict.get("Section C", ""), 10

        if not raw_ans: return None
        clean_ans = "".join([char for char in raw_ans if char.isalpha()])
        return clean_ans[:expected_len] if len(clean_ans) >= expected_len else clean_ans

    # ==========================================
    # 📖 阅读真题引擎
    # ==========================================
    @filter.command(cfg.get("command_draw_reading", "来篇阅读"))
    async def draw_question(self, event: AstrMessageEvent):
        if not self.questions:
            yield event.plain_result("⚠️ 阅读题库未加载。")
            return
            
        user_id = str(event.get_sender_id())
        self.cleanup_sessions()
        
        done_list = self.done_readings_db.get(user_id, [])
        available_questions = []
        for q in self.questions:
            q_id = self.get_q_id(q['meta'], q['type'])
            if q_id not in done_list and self.get_answer_key(q['meta'], q['type']):
                available_questions.append(q)

        if not available_questions:
            yield event.plain_result("🎉 天呐！你居然刷完了题库里所有的六级阅读真题！你这词汇和阅读量已经无敌了！")
            return

        item = random.choice(available_questions)
        meta, sec_type = item['meta'], item['type']
        correct_ans = self.get_answer_key(meta, sec_type)
        q_id = self.get_q_id(meta, sec_type)
        
        self.user_sessions[user_id] = {
            "correct_ans": correct_ans, 
            "sec_type": sec_type, 
            "meta": meta, 
            "q_id": q_id,
            "time": time.time()
        }
        
        ans_cmd = cfg.get("command_submit_answer", "答案")
        chk_cmd = cfg.get("command_check_answer", "查答案")
        progress_str = f" [进度: {len(done_list)}/{len(self.questions)}]"
        
        reply = f"📜 考卷锁定: {meta.get('year')}年 {meta.get('month')}月 第{meta.get('set_index')}套 | {sec_type}{progress_str}\n" + "=" * 25 + "\n"
        reply += item['content'] + f"\n\n💡 提示：本题共 {len(correct_ans)} 道题。\n👉 做完请回复：/{ans_cmd} ABCD\n👉 纯阅读想看答案回复：/{chk_cmd}"
        yield event.plain_result(reply)

    def mark_question_done(self, user_id, q_id):
        if user_id not in self.done_readings_db: self.done_readings_db[user_id] = []
        if q_id not in self.done_readings_db[user_id]:
            self.done_readings_db[user_id].append(q_id)
            self.save_done_readings()

    @filter.command(cfg.get("command_check_answer", "查答案"))
    async def check_answer(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        self.cleanup_sessions() 
        draw_cmd = cfg.get("command_draw_reading", "来篇阅读")
        if user_id not in self.user_sessions:
            yield event.plain_result(f"🤔 没找到你正在做的题哦，先发 '/{draw_cmd}' 抽一篇吧！")
            return
        session = self.user_sessions[user_id]
        reply = f"🤫 【 答案揭晓 】\n题目：{session['meta'].get('year')}年 {session['meta'].get('month')}月 第{session['meta'].get('set_index')}套 | {session['sec_type']}\n正确答案是：{session['correct_ans']}\n"
        reply += "=" * 20 + f"\n(本题已标记为“已刷”，想挑战新题请发送 '/{draw_cmd}')"
        self.mark_question_done(user_id, session["q_id"])
        del self.user_sessions[user_id]
        yield event.plain_result(reply)

    @filter.command(cfg.get("command_submit_answer", "答案"))
    async def grade_question(self, event: AstrMessageEvent, user_ans: str = ""):
        ans_cmd = cfg.get("command_submit_answer", "答案")
        if not user_ans:
            yield event.plain_result(f"⚠️ 交白卷可不行哦！请加上你的选项，例如：/{ans_cmd} ABCD")
            return
        user_id = str(event.get_sender_id())
        self.cleanup_sessions() 
        draw_cmd = cfg.get("command_draw_reading", "来篇阅读")
        if user_id not in self.user_sessions:
            yield event.plain_result(f"🤔 没找到你的做题记录，请重新发送 '/{draw_cmd}'。")
            return
        session = self.user_sessions[user_id]
        correct_ans, sec_type = session["correct_ans"].upper(), session["sec_type"].upper()
        user_ans = user_ans.upper().replace(" ", "")
        
        if "A" in sec_type: start_num = 26
        elif "B" in sec_type: start_num = 36
        elif "C" in sec_type:
            if "2" in sec_type or "TWO" in sec_type: start_num = 51
            else: start_num = 46 
        else: start_num = 1
            
        score, results = 0, []
        for i in range(len(correct_ans)):
            u = user_ans[i] if i < len(user_ans) else "_"
            c = correct_ans[i]
            q_num = start_num + i
            if u == c: score += 1; results.append(f"第 {q_num} 题: ✅")
            else: results.append(f"第 {q_num} 题: ❌ (你的:{u} -> 正确:{c})")
            
        reply = f"📊 【 批改报告 】 得分: {score} / {len(correct_ans)}\n" + "-" * 20 + "\n" + "\n".join(results)
        reply += f"\n" + "-" * 20 + f"\n(本题已标记为“已刷”，想挑战新题请发送 '/{draw_cmd}')"
        
        self.mark_question_done(user_id, session["q_id"])
        del self.user_sessions[user_id]
        yield event.plain_result(reply)

    # ==========================================
    # 🔍 单词核武器模块
    # ==========================================
    @filter.command(cfg.get("command_random_vocab", "抽单词"))
    async def random_vocab(self, event: AstrMessageEvent):
        if not self.vocab_random_list:
            yield event.plain_result("⚠️ 乱序单词表未加载。")
            return
        words = random.sample(self.vocab_random_list, min(5, len(self.vocab_random_list)))
        reply = "🔥 【 单 词 闪 测 】 🔥\n" + "=" * 20 + "\n"
        for i, w in enumerate(words): reply += f"{i+1}. {w}\n"
        add_cmd = cfg.get("command_add_vocab", "加生词")
        reply += "=" * 20 + f"\n👉 认识几个？遇到不会的可以直接发送 '/{add_cmd} [单词]'"
        yield event.plain_result(reply)

    @filter.command(cfg.get("command_search_vocab", "查单词"))
    async def search_vocab(self, event: AstrMessageEvent, target_word: str = ""):
        search_cmd = cfg.get("command_search_vocab", "查单词")
        if not target_word:
            yield event.plain_result(f"⚠️ 你想查什么单词呀？例如：/{search_cmd} insight")
            return
        target_word = target_word.strip().lower()
        if target_word in self.vocab_fast_dict:
            found_info = self.vocab_fast_dict[target_word]
            add_cmd = cfg.get("command_add_vocab", "加生词")
            yield event.plain_result(f"📖 【 {target_word} 】的查询结果：\n{found_info}\n\n💡 遇到生词？回复 `/{add_cmd} {target_word}` 加入记忆库！")
        else:
            yield event.plain_result(f"🙈 没找到 '{target_word}' 的记录哦。")

    # ==========================================
    # 🧠 艾宾浩斯核心引擎
    # ==========================================
    @filter.command(cfg.get("command_my_stats", "我的词库"))
    async def my_stats(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        active_count = len(self.user_vocab_db.get(user_id, {}))
        mastered_count = len(self.mastered_vocab_db.get(user_id, {}))
        done_reading_count = len(self.done_readings_db.get(user_id, [])) 
        total_reading_count = len(self.questions)
        
        reply = f"📊 【 个人私教战绩 】\n"
        reply += "=" * 20 + "\n"
        reply += f"🔥 正在渡劫单词：{active_count} 个\n"
        reply += f"🎓 永久掌握单词：{mastered_count} 个\n"
        reply += f"📚 阅读真题进度：{done_reading_count} / {total_reading_count} 篇\n"
        reply += "=" * 20 + "\n"
        
        if mastered_count == 0 and active_count == 0 and done_reading_count == 0:
            reply += "所有的纪录都是0呢，今天就正式拔剑开战吧！"
        else:
            reply += "汗水绝对不会骗人，继续保持这股冲劲！"
        yield event.plain_result(reply)

    @filter.command(cfg.get("command_get_new", "今日新词"))
    async def get_new_words(self, event: AstrMessageEvent, count: int = 35):
        user_id = str(event.get_sender_id())
        if not self.vocab_random_list or not self.vocab_fast_dict:
            yield event.plain_result("⚠️ 词库未加载成功，无法获取新词。")
            return

        if user_id not in self.user_vocab_db: self.user_vocab_db[user_id] = {}
        if user_id not in self.mastered_vocab_db: self.mastered_vocab_db[user_id] = {} 
        
        unlearned_words = []
        for word in self.vocab_random_list:
            w_lower = word.strip().lower()
            if w_lower not in self.user_vocab_db[user_id] and w_lower not in self.mastered_vocab_db[user_id]:
                unlearned_words.append(w_lower)
            if len(unlearned_words) >= count:
                break

        if not unlearned_words:
            yield event.plain_result("🎉 太神了！大词库里的几千个单词已经被你全部过完啦！")
            return

        now = time.time()
        reply = f"🆕 【 每日新词积攒 】 目标: {len(unlearned_words)} 词\n" + "=" * 25 + "\n"
        
        for idx, word in enumerate(unlearned_words):
            self.user_vocab_db[user_id][word] = {
                "add_time": now, "stage": 0, "next_review": now + EBBINGHAUS_INTERVALS[0]
            }
            meaning = self.vocab_fast_dict.get(word, "释义丢失")
            if len(meaning) > 40: meaning = meaning[:40] + "..."
            reply += f"{idx+1}. {word}  {meaning}\n"

        self.save_user_vocab()
        alarm_cmd = cfg.get("command_set_alarm", "复习提醒")
        reply += "=" * 25 + f"\n✨ 这 {len(unlearned_words)} 个新词已正式编入你的艾宾浩斯战区！\n(发送 `/{alarm_cmd}` 设定系统自动催命时间)"
        yield event.plain_result(reply)

    @filter.command(cfg.get("command_add_vocab", "加生词"))
    async def add_vocab(self, event: AstrMessageEvent, target_word: str = ""):
        add_cmd = cfg.get("command_add_vocab", "加生词")
        if not target_word:
            yield event.plain_result(f"⚠️ 你想添加什么生词呀？例如：/{add_cmd} insight")
            return

        user_id = str(event.get_sender_id())
        target_word = target_word.strip().lower()

        if target_word not in self.vocab_fast_dict:
            yield event.plain_result(f"⚠️ 词库里没有 '{target_word}'，无法添加。请检查拼写！")
            return

        if user_id not in self.user_vocab_db: self.user_vocab_db[user_id] = {}
        if user_id not in self.mastered_vocab_db: self.mastered_vocab_db[user_id] = {}
        
        if target_word in self.user_vocab_db[user_id]:
            yield event.plain_result(f"✅ '{target_word}' 已经在你的生词本里啦！")
            return
            
        if target_word in self.mastered_vocab_db[user_id]:
            yield event.plain_result(f"🎓 '{target_word}' 已经是你永久掌握的词汇了！难道又忘了？我已帮你重新拉回复习列表！")
            del self.mastered_vocab_db[user_id][target_word] 
            self.save_mastered_vocab()

        now = time.time()
        self.user_vocab_db[user_id][target_word] = {
            "add_time": now, "stage": 0, "next_review": now + EBBINGHAUS_INTERVALS[0]
        }
        self.save_user_vocab()
        
        alarm_cmd = cfg.get("command_set_alarm", "复习提醒")
        human_time = self.get_human_time(now + EBBINGHAUS_INTERVALS[0])
        yield event.plain_result(f"📚 成功将 '{target_word}' 收入生词本！\n[当前境界: {RANKS[0]}]\n下次复习时间：{human_time}。")

    def generate_review_report(self, user_id):
        if user_id not in self.user_vocab_db or not self.user_vocab_db[user_id]: return None
        now = time.time()
        due_words, graduated_words = [], []

        for word, data in self.user_vocab_db[user_id].items():
            if now >= data["next_review"]: due_words.append(word)

        if not due_words: return None

        reply = f"⏰ 【 艾宾浩斯每日打卡 】 共 {len(due_words)} 个词\n" + "=" * 25 + "\n"
        for idx, word in enumerate(due_words):
            meaning = self.vocab_fast_dict.get(word, "释义丢失")
            if len(meaning) > 100: meaning = meaning[:100] + "..."
            
            current_stage = self.user_vocab_db[user_id][word]["stage"]
            if current_stage + 1 < len(EBBINGHAUS_INTERVALS):
                new_stage = current_stage + 1
                self.user_vocab_db[user_id][word]["stage"] = new_stage
                next_time = now + EBBINGHAUS_INTERVALS[new_stage]
                self.user_vocab_db[user_id][word]["next_review"] = next_time
                
                rank_str = RANKS[new_stage]
                human_time = self.get_human_time(next_time)
                reply += f"{idx+1}. {word}\n   └ {meaning}\n   [阶段: {rank_str} | 下次: {human_time}]\n"
            else:
                graduated_words.append(word)
                reply += f"{idx+1}. {word}\n   └ {meaning}\n   [🎉 境界圆满，光荣毕业！]\n"

        forget_cmd = cfg.get("command_forget_vocab", "忘")
        reply += "=" * 25 + f"\n✨ 以上单词已自动升级！\n⚠️ 没记住？回复 `/{forget_cmd} [单词]` 降级重排！"

        if graduated_words:
            if user_id not in self.mastered_vocab_db: self.mastered_vocab_db[user_id] = {}
            for gw in graduated_words: 
                self.mastered_vocab_db[user_id][gw] = {
                    "graduated_time": now, "meaning": self.vocab_fast_dict.get(gw, "释义丢失")
                }
                del self.user_vocab_db[user_id][gw] 
            self.save_mastered_vocab() 

        self.save_user_vocab()
        return reply

    @filter.command(cfg.get("command_review_vocab", "今日复习"))
    async def review_vocab(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        reply = self.generate_review_report(user_id)
        if reply: yield event.plain_result(reply)
        else: yield event.plain_result("🎉 太棒了！今天你没有需要复习的生词！")

    @filter.command(cfg.get("command_forget_vocab", "忘"))
    async def forget_vocab(self, event: AstrMessageEvent, target_word: str = ""):
        forget_cmd = cfg.get("command_forget_vocab", "忘")
        if not target_word:
            yield event.plain_result(f"⚠️ 请加上没记住的单词，例如：/{forget_cmd} abandon")
            return

        user_id = str(event.get_sender_id())
        target_word = target_word.strip().lower()

        if user_id not in self.user_vocab_db or target_word not in self.user_vocab_db[user_id]:
            yield event.plain_result(f"🤔 你的生词本里目前没有 '{target_word}' 正在复习哦。")
            return

        current_stage = self.user_vocab_db[user_id][target_word]["stage"]
        new_stage = max(0, current_stage - 2) 
        now = time.time()
        next_time = now + EBBINGHAUS_INTERVALS[new_stage]
        
        self.user_vocab_db[user_id][target_word]["stage"] = new_stage
        self.user_vocab_db[user_id][target_word]["next_review"] = next_time
        self.save_user_vocab()
        
        rank_str = RANKS[new_stage]
        human_time = self.get_human_time(next_time)
        yield event.plain_result(f"📉 记忆受挫，已将 '{target_word}' 降级至【{rank_str}】。\n下次复习已调整为：{human_time}。请加强记忆！")

    # ==========================================
    # 🔔 订阅提醒模块
    # ==========================================
    @filter.command(cfg.get("command_set_alarm", "复习提醒"))
    async def set_alarm(self, event: AstrMessageEvent, time_str: str = "08:00"):
        user_id = str(event.get_sender_id())
        try: datetime.strptime(time_str, "%H:%M")
        except ValueError:
            yield event.plain_result("⚠️ 时间格式不对哦，请使用 24 小时制，比如：/复习提醒 08:30")
            return

        platform = event.message_obj.platform
        session_id = event.message_obj.session_id

        self.subscribers[user_id] = {
            "platform": platform, "session_id": session_id,
            "time": time_str, "notified_today": False
        }
        self.save_subscribers()
        yield event.plain_result(f"✅ 设置成功！我以后会在每天的 {time_str} 主动把复习词汇发给你，加油！")
