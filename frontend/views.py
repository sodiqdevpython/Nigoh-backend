from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login
from django.contrib import messages
from django.contrib.auth import logout
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Prefetch
from endpoints.models import Group, Computer # BuildingNumber modelingizni import qiling
from tracking.models import RemoteControlSession
from endpoints.choices import BuildingNumber, Floor
from .forms import GroupForm
from django.http import JsonResponse
from django.core.paginator import Paginator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from tracking.models import AppUsageStatistic, ActivityLog, BlockedAttemptLog, ProcessAlertLog, ScreenShareSession, BlockedURL, BlockedProcess
from endpoints.consumers import LIVE_METRICS
import json
import hashlib
from datetime import datetime
from datetime import timedelta
from django.utils import timezone

def get_secure_token():
    secret_word = "sodiq2005.py"
    today = datetime.now().strftime("%Y-%m-%d")
    raw_string = f"{secret_word}-{today}"
    return hashlib.sha256(raw_string.encode()).hexdigest()

def login_view(request):
    # 1. Agar foydalanuvchi allaqachon tizimga kirgan bo'lsa, asosiy sahifaga yo'naltiramiz
    if request.user.is_authenticated:
        return redirect('home')

    # 2. Agar forma jo'natilgan bo'lsa (POST so'rov)
    if request.method == 'POST':
        # HTML dagi 'name' atributlari orqali ma'lumotlarni tortib olamiz
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me')

        # Bazadan shunday foydalanuvchi borligini va paroli to'g'riligini tekshiramiz
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Parol to'g'ri, tizimga kiritamiz
            auth_login(request, user)
            
            # "Eslab qolish" mantiqi
            if not remember_me:
                # Agar ptichka qo'yilmagan bo'lsa, brauzer yopilishi bilan sessiya o'chadi
                request.session.set_expiry(0)
            else:
                # Agar ptichka qo'yilgan bo'lsa, sessiya odatiy vaqtgacha (masalan 2 hafta) saqlanadi
                # Buni settings.py da SESSION_COOKIE_AGE orqali o'zgartirishingiz mumkin
                pass 
                
            # Muvaffaqiyatli kirgandan keyin yo'naltiriladigan sahifa
            return redirect('home') 
        else:
            # Parol yoki login xato bo'lsa, xabar chiqaramiz
            messages.error(request, "Foydalanuvchi nomi yoki parol noto'g'ri. Iltimos, qayta urinib ko'ring.")
            return redirect('login') # Xatolik bilan yana login sahifasida qoladi

    # 3. Oddiy GET so'rov bo'lsa, shunchaki sahifani ochib beradi
    return render(request, 'auth/login.html')

def logout_view(request):
    """Foydalanuvchini tizimdan chiqarish"""
    logout(request) # Sessiyani va cookie larni tozalaydi
    return redirect('login')


def home(request):
    return render(request, 'base/base.html')


def group_management(request):
    # --- POST SO'ROVLAR (Create, Update, Delete) ---
    if request.method == 'POST':
        action = request.POST.get('action') # Qaysi amal bajarilayotganini aniqlaymiz

        if action == 'create':
            form = GroupForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Guruh muvaffaqiyatli qo'shildi!")
            return redirect('group_management')

        # TAHRIRLASH (UPDATE)
        elif action == 'update':
            group_id = request.POST.get('group_id')
            group = get_object_or_404(Group, id=group_id)
            
            # Yangi ma'lumotlarni o'zlashtiramiz
            group.name = request.POST.get('name')
            group.building = request.POST.get('building')
            group.floor = request.POST.get('floor')     # <--- SHU QATORNI QO'SHING
            group.room_number = request.POST.get('room_number')
            
            group.save() # Bazaga saqlaymiz!
            
            messages.success(request, f"{group.name} guruhi muvaffaqiyatli yangilandi!")

        elif action == 'delete':
            group_id = request.POST.get('group_id')
            group = get_object_or_404(Group, id=group_id)
            group.delete()
            messages.success(request, "Guruh o'chirildi!")
            return redirect('group_management')

    # --- GET SO'ROVLAR (Read, Search, Filter, Pagination) ---
    query = request.GET.get('q', '')
    building_filter = request.GET.get('building', '')

    groups = Group.objects.all().order_by('-id')

    # Qidiruv (Search) - nomi yoki xona raqami bo'yicha
    if query:
        groups = groups.filter(
            Q(name__icontains=query) | 
            Q(room_number__icontains=query)
        )

    # Filtr (Filter) - Bino bo'yicha
    if building_filter:
        groups = groups.filter(building=building_filter)

    # Paginatsiya (Pagination) - Har sahifada 10 ta
    paginator = Paginator(groups, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'form': GroupForm(), # Create uchun bo'sh forma
        'query': query,
        'building_filter': building_filter,
        'building_choices': BuildingNumber.choices, # Filtr dropdown uchun
        'floor_choices': Floor.choices,
    }
    
    return render(request, 'menu/groups/groups.html', context)


def device_list_view(request):
    # 1. URL dan barcha filtr parametrlarini olamiz
    search_query = request.GET.get('search', '')
    building_id = request.GET.get('building', '')
    floor_id = request.GET.get('floor', '')
    group_id = request.GET.get('group', '')

    # 2. Barcha kompyuterlarni chaqiramiz
    computers = Computer.objects.select_related('group').order_by('hostname')

    # 3. Izlash (Nomi yoki UUID)
    if search_query:
        computers = computers.filter(
            Q(hostname__icontains=search_query) |
            Q(bios_uuid__icontains=search_query)
        )

    # ==========================================
    # 4. AQLLI FILTRLAR (Bino, Qavat, Xona)
    # ==========================================
    
    # Agar bino tanlangan bo'lsa, faqat shu binodagi guruhlarga tegishli kompyuterlarni oladi
    if building_id:
        computers = computers.filter(group__building=building_id)
        
    # Agar qavat tanlangan bo'lsa, shu qavatni oladi (Binoga ulanib ketaveradi)
    if floor_id:
        computers = computers.filter(group__floor=floor_id)

    # Aniq bir xona (guruh) yoki "Guruhsiz" qurilmalar
    if group_id:
        if group_id == 'none':
            computers = computers.filter(group__isnull=True)
        else:
            computers = computers.filter(group_id=group_id)

    # 5. Paginatsiya
    paginator = Paginator(computers, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 6. Dropdownlar (Select) uchun ma'lumotlarni HTML ga jo'natamiz
    # Group modelidan building va floor uchun 'choices' larni aqlli tarzda avtomat olamiz:
    building_choices = Group._meta.get_field('building').choices
    floor_choices = Group._meta.get_field('floor').choices
    groups = Group.objects.all().order_by('name')

    context = {
        'page_obj': page_obj,
        'groups': groups,
        'building_choices': building_choices,
        'floor_choices': floor_choices,
        'search_query': search_query,
        'current_building': building_id,
        'current_floor': floor_id,
        'current_group': group_id,
    }
    return render(request, 'menu/device/device_list.html', context)


@login_required
def create_remote_session_view(request, bios_uuid):
    if request.method == 'POST':
        computer = get_object_or_404(Computer, bios_uuid=bios_uuid)
        
        if not computer.is_online:
            return JsonResponse({"error": "Bu kompyuter hozir oflayn."}, status=400)

        # 1. BAZADAN SHU KOMPYUTERGA TEGISHLI BARCHA ESKI SESSIYALARNI O'CHIRAMIZ
        RemoteControlSession.objects.filter(computer=computer).delete()

        try:
            data = json.loads(request.body)
            duration = data.get('time', 300)
        except:
            duration = 300

        # 2. Yangi sessiya yaratamiz
        session = RemoteControlSession.objects.create(
            author=request.user,
            computer=computer,
            duration=duration,
            is_active=False
        )

        # 3. Agentga xabar yuboramiz
        channel_layer = get_channel_layer()
        group_name = f"pc_{bios_uuid}" 
        
        command_payload = {
            "type": "remote_controll",
            "action": duration,
            "payload": {
                "session_id": str(session.id)
            }
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "execute_command", 
                "data": command_payload
            }
        )

        # Frontend'ga yaratilgan session_id ni qaytaramiz (Polling uchun kerak bo'ladi)
        return JsonResponse({
            "status": "pending",
            "session_id": session.id
        }, status=201)

    return JsonResponse({"error": "Faqat POST so'rov qabul qilinadi!"}, status=405)


# FRONTEND HAR 2 SONIYADA SHU YERDAN JAVOB KUTADI
@login_required
def check_session_status_view(request, session_id):
    session = get_object_or_404(RemoteControlSession, id=session_id)
    return JsonResponse({
        "is_active": session.is_active,
        "stream_url": session.stream_url
    })


def device_detail_view(request, pk):
    computer = get_object_or_404(Computer, id=pk)

    if request.GET.get('metrics_only') == '1':
        return JsonResponse(LIVE_METRICS.get(computer.bios_uuid) or {})

    current_tab = request.GET.get('tab', 'usage')
    search_query = request.GET.get('search', '')
    
    # VAQT FILTRINI OLISH (Default: 'today' - Bugun)
    time_filter = request.GET.get('time', 'today') 

    latest_rc = RemoteControlSession.objects.filter(computer=computer).order_by('-created_at').first()
    latest_stream_url = latest_rc.stream_url if latest_rc and latest_rc.stream_url else None

    # Oxirida slash (/) bo'lsa, olib tashlaymiz (ikkita slash bo'lib qolmasligi uchun)
    if latest_stream_url and latest_stream_url.endswith('/'):
        latest_stream_url = latest_stream_url[:-1]
    
    context = {
        'computer': computer,
        'current_tab': current_tab,
        'search_query': search_query,
        'time_filter': time_filter,
        'secure_token': get_secure_token(),
        'latest_stream_url': latest_stream_url,
        'live_metrics': LIVE_METRICS.get(computer.bios_uuid),
    }

    # ==========================================
    # CHART UCHUN VAQT ORALIQLARINI HISOBLASH
    # ==========================================
    now = timezone.now()
    
    # Default sifatida "Bugun" 00:00 dan boshlanadi
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if time_filter == 'week':
        # Shu haftaning Dushanba kunidan boshlab
        start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif time_filter == 'month':
        # Shu oyning 1-sanasidan boshlab
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Chartlar uchun bazaviy so'rov (Faqat tanlangan vaqtdan keyingilarni olamiz - Server tezligi oshadi)
    app_qs = AppUsageStatistic.objects.filter(computer=computer, created_at__gte=start_date)
    act_qs = ActivityLog.objects.filter(computer=computer, created_at__gte=start_date)

    # ==========================================
    # CHART UCHUN TOP 10 STATISTIKALARNI TAYYORLASH (GURUHLASH)
    # ==========================================
    
    # 1. Top 10 Dasturlar (app_name bo'yicha guruhlaymiz va vaqtini qo'shamiz)
    top_apps = app_qs.values('app_name')\
        .annotate(total_active=Sum('active_seconds'))\
        .order_by('-total_active')[:10]
        
    context['app_chart_labels'] = json.dumps([app['app_name'] for app in top_apps])
    context['app_chart_data'] = json.dumps([app['total_active'] for app in top_apps])

    # 2. Top 10 Faollik/Vebsaytlar (Oyna sarlavhasi 'title' bo'yicha guruhlaymiz)
    top_activities = act_qs.values('title')\
        .annotate(total_duration=Sum('duration_seconds'))\
        .order_by('-total_duration')[:10]
        
    act_labels = []
    for act in top_activities:
        title = act['title'] or "Nomsiz oyna"
        act_labels.append((title[:30] + '...') if len(title) > 30 else title)
        
    context['act_chart_labels'] = json.dumps(act_labels)
    context['act_chart_data'] = json.dumps([act['total_duration'] for act in top_activities])

    # ==========================================
    # TABLAR VA JADVALLAR UCHUN ASOSIY MA'LUMOTLAR
    # ==========================================
    qs = None

    if current_tab == 'usage':
        qs = AppUsageStatistic.objects.filter(computer=computer).order_by('-active_seconds')
        if search_query:
            qs = qs.filter(app_name__icontains=search_query)

    elif current_tab == 'activity':
        qs = ActivityLog.objects.filter(computer=computer).order_by('-created_at')
        if search_query:
            qs = qs.filter(Q(app_name__icontains=search_query) | Q(title__icontains=search_query))

    elif current_tab == 'web_blocked':
        qs = BlockedAttemptLog.objects.filter(computer=computer).select_related('url').order_by('-created_at')
        if search_query:
            qs = qs.filter(url__url_address__icontains=search_query)

    elif current_tab == 'app_blocked':
        qs = ProcessAlertLog.objects.filter(computer=computer).select_related('process_rule').order_by('-created_at')
        if search_query:
            qs = qs.filter(app_name__icontains=search_query)
            
    elif current_tab == 'sessions':
        qs = ScreenShareSession.objects.filter(computer=computer).order_by('-created_at')

    if qs is not None:
        paginator = Paginator(qs, 15)
        page_number = request.GET.get('page')
        context['page_obj'] = paginator.get_page(page_number)

    return render(request, 'menu/device/device_detail.html', context)


def group_detail_view(request, pk):
    group = get_object_or_404(Group, id=pk)
    computers = Computer.objects.filter(group=group).order_by('hostname')

    total_count = computers.count()
    online_count = computers.filter(is_online=True).count()

    context = {
        'group': group,
        'computers': computers,
        'total_count': total_count,
        'online_count': online_count,
        'offline_count': total_count - online_count,
        'live_metrics': LIVE_METRICS,
    }
    return render(request, 'menu/groups/group_detail.html', context)


def group_metrics_view(request, pk):
    group = get_object_or_404(Group, id=pk)
    computers = Computer.objects.filter(group=group).values(
        'bios_uuid', 'hostname', 'is_online', 'id', 'ram_gb', 'last_seen'
    )

    result = {}
    for pc in computers:
        last_seen = pc['last_seen']
        if last_seen:
            # Toshkent vaqtiga o'tkazamiz va formatlayamiz
            from django.utils import timezone as tz
            local_time = last_seen.astimezone(tz.get_current_timezone())
            last_seen_str = local_time.strftime('%d.%m.%Y %H:%M')
        else:
            last_seen_str = '—'

        result[pc['bios_uuid']] = {
            'hostname':  pc['hostname'],
            'is_online': pc['is_online'],
            'pk':        pc['id'],
            'ram_gb':    float(pc['ram_gb'] or 0),
            'last_seen': last_seen_str,
            'metrics':   LIVE_METRICS.get(pc['bios_uuid']) or {},
        }
    online_total = sum(1 for v in result.values() if v['is_online'])
    return JsonResponse({'pcs': result, 'online_count': online_total, 'total_count': len(result)})


def group_command_view(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    group = get_object_or_404(Group, id=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    command = data.get('command', '')
    url_param = data.get('url', '').strip()
    target_uuid = data.get('target_uuid', '')

    command_map = {
        'lock':     'rundll32.exe user32.dll,LockWorkStation',
        'restart':  'shutdown /r /t 10',
        'shutdown': 'shutdown /s /t 10',
    }

    if command == 'open_url':
        if not url_param:
            return JsonResponse({'error': "URL kiriting"}, status=400)
        if not (url_param.startswith('http://') or url_param.startswith('https://')):
            url_param = 'https://' + url_param
        shell_cmd = f'explorer.exe "{url_param}"'
    elif command in command_map:
        shell_cmd = command_map[command]
    else:
        return JsonResponse({'error': "Noto'g'ri buyruq"}, status=400)

    channel_layer = get_channel_layer()

    if target_uuid:
        computer = get_object_or_404(Computer, bios_uuid=target_uuid, group=group)
        if not computer.is_online:
            return JsonResponse({'error': 'Bu PC oflayn', 'sent': 0})
        async_to_sync(channel_layer.group_send)(
            f'pc_{target_uuid}',
            {'type': 'execute_command', 'data': {'type': 'do_command', 'action': shell_cmd, 'message': '', 'payload': {}}}
        )
        sent = 1
    else:
        online_count = Computer.objects.filter(group=group, is_online=True).count()
        async_to_sync(channel_layer.group_send)(
            f'group_{pk}',
            {'type': 'execute_command', 'data': {'type': 'do_command', 'action': shell_cmd, 'message': '', 'payload': {}}}
        )
        sent = online_count

    return JsonResponse({'status': 'ok', 'sent': sent})


def device_command_view(request, pk):
    """Bitta qurilmaga buyruq yuborish"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    computer = get_object_or_404(Computer, id=pk)
    if not computer.is_online:
        return JsonResponse({'error': 'Qurilma oflayn', 'sent': 0})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    command   = data.get('command', '').strip()
    url_param = data.get('url', '').strip()
    path_param = data.get('path', '').strip()

    command_map = {
        'lock':     'rundll32.exe user32.dll,LockWorkStation',
        'restart':  'shutdown /r /t 10',
        'shutdown': 'shutdown /s /t 10',
    }

    if command == 'kill_process':
        shell_cmd = data.get('path', '').strip()  # JS tayyorlab yuboradi
        if not shell_cmd or 'taskkill' not in shell_cmd:
            return JsonResponse({'error': "Jarayon nomi kiritilmadi"}, status=400)

    elif command == 'open_url':
        if not url_param:
            return JsonResponse({'error': "URL kiriting"}, status=400)
        if not (url_param.startswith('http://') or url_param.startswith('https://')):
            url_param = 'https://' + url_param
        # explorer.exe — terminal ochilmaydi, brauzerda ochiladi
        shell_cmd = f'explorer.exe "{url_param}"'

    elif command == 'delete_path':
        if not path_param:
            return JsonResponse({'error': "Yo'l kiritilmadi"}, status=400)
        # Tizim papkalaridan himoya
        forbidden = ['C:\\Windows', 'C:\\Program Files', 'C:\\Users\\All Users', 'C:\\ProgramData\\Nigoh']
        if any(path_param.lower().startswith(f.lower()) for f in forbidden):
            return JsonResponse({'error': "Bu yo'lni o'chirish taqiqlangan"}, status=403)
        # Papkani o'chirish: rd, faylni o'chirish: del
        shell_cmd = f'cmd /c (rd /s /q "{path_param}" 2>nul || del /f /q "{path_param}" 2>nul)'

    elif command in command_map:
        shell_cmd = command_map[command]

    else:
        return JsonResponse({'error': "Noto'g'ri buyruq"}, status=400)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'pc_{computer.bios_uuid}',
        {'type': 'execute_command', 'data': {'type': 'do_command', 'action': shell_cmd, 'message': '', 'payload': {}}}
    )
    return JsonResponse({'status': 'ok', 'command': command})


def group_stats_view(request, pk):
    group = get_object_or_404(Group, id=pk)
    time_filter = request.GET.get('time', 'today')

    now = timezone.now()
    if time_filter == 'week':
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        label = 'Shu hafta'
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = 'Bugun'

    computers = Computer.objects.filter(group=group)

    # Top web sahifalar — eng ko'p tashrif (count)
    top_pages_count = (
        ActivityLog.objects
        .filter(computer__in=computers, created_at__gte=start, url__isnull=False)
        .exclude(url='')
        .values('url', 'title')
        .annotate(visits=Count('id'), total_sec=Sum('duration_seconds'))
        .order_by('-visits')[:10]
    )

    # Top web sahifalar — eng ko'p vaqt (duration)
    top_pages_time = (
        ActivityLog.objects
        .filter(computer__in=computers, created_at__gte=start, url__isnull=False)
        .exclude(url='')
        .values('url', 'title')
        .annotate(total_sec=Sum('duration_seconds'), visits=Count('id'))
        .order_by('-total_sec')[:10]
    )

    # Top dasturlar — eng ko'p vaqt
    top_apps = (
        AppUsageStatistic.objects
        .filter(computer__in=computers, created_at__gte=start)
        .values('app_name')
        .annotate(total_sec=Sum('active_seconds'))
        .order_by('-total_sec')[:10]
    )

    context = {
        'group': group,
        'time_filter': time_filter,
        'label': label,
        'top_pages_count': top_pages_count,
        'top_pages_time': top_pages_time,
        'top_apps': top_apps,
        'total_computers': computers.count(),
    }
    return render(request, 'menu/groups/group_stats.html', context)


def blocked_urls_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            url_address = request.POST.get('url_address', '').strip()
            if url_address:
                BlockedURL.objects.get_or_create(url_address=url_address)
                messages.success(request, f"'{url_address}' muvaffaqiyatli bloklandi!")
            return redirect('blocked_urls')

        elif action == 'update':
            obj_id = request.POST.get('obj_id')
            obj = get_object_or_404(BlockedURL, id=obj_id)
            obj.url_address = request.POST.get('url_address', '').strip()
            obj.save()
            messages.success(request, "URL muvaffaqiyatli yangilandi!")
            return redirect('blocked_urls')

        elif action == 'delete':
            obj_id = request.POST.get('obj_id')
            get_object_or_404(BlockedURL, id=obj_id).delete()
            messages.success(request, "URL o'chirildi!")
            return redirect('blocked_urls')

    search_query = request.GET.get('search', '')
    urls_qs = BlockedURL.objects.all().order_by('-created_at')
    if search_query:
        urls_qs = urls_qs.filter(url_address__icontains=search_query)

    # Top 5 eng ko'p urinish bo'lgan URLlar
    top_attempts = (
        BlockedAttemptLog.objects
        .values('url__url_address', 'url__id')
        .annotate(total=Sum('attempts_count'))
        .order_by('-total')[:5]
    )

    paginator = Paginator(urls_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'menu/blocked_urls/blocked_urls.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'top_attempts': top_attempts,
    })


def blocked_processes_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name', '').strip()
            match_type = request.POST.get('match_type', 'PROCESS')
            description = request.POST.get('description', '').strip()
            if name:
                BlockedProcess.objects.get_or_create(
                    name=name,
                    defaults={'match_type': match_type, 'description': description}
                )
                messages.success(request, f"'{name}' jarayoni muvaffaqiyatli bloklandi!")
            return redirect('blocked_processes')

        elif action == 'update':
            obj_id = request.POST.get('obj_id')
            obj = get_object_or_404(BlockedProcess, id=obj_id)
            obj.name = request.POST.get('name', '').strip()
            obj.match_type = request.POST.get('match_type', 'PROCESS')
            obj.description = request.POST.get('description', '').strip()
            obj.save()
            messages.success(request, "Jarayon muvaffaqiyatli yangilandi!")
            return redirect('blocked_processes')

        elif action == 'delete':
            obj_id = request.POST.get('obj_id')
            get_object_or_404(BlockedProcess, id=obj_id).delete()
            messages.success(request, "Jarayon o'chirildi!")
            return redirect('blocked_processes')

    search_query = request.GET.get('search', '')
    match_filter = request.GET.get('match_type', '')
    procs_qs = BlockedProcess.objects.all().order_by('-created_at')
    if search_query:
        procs_qs = procs_qs.filter(name__icontains=search_query)
    if match_filter:
        procs_qs = procs_qs.filter(match_type=match_filter)

    # Top 5 eng ko'p bloklangan jarayonlar
    top_blocked = (
        ProcessAlertLog.objects
        .values('process_rule__name', 'process_rule__id')
        .annotate(total=Sum('attempts_count'))
        .order_by('-total')[:5]
    )

    paginator = Paginator(procs_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'menu/blocked_processes/blocked_processes.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'match_filter': match_filter,
        'top_blocked': top_blocked,
        'match_choices': BlockedProcess.MATCH_CHOICES,
    })
    