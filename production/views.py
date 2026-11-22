from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from accounts.models import Role
from accounts.permissions import role_required
from .models import ProductionRun, ProductionRunItem
from .forms import ProductionRunCreateForm, ProductionOutputForm
from .services import (
    create_production_run,
    issue_materials_for_run,
    record_production_output,
)

PRODUCTION_MANAGERS = [Role.ADMIN, Role.PRODUCTION]
PRODUCTION_VIEWERS = [Role.ADMIN, Role.PRODUCTION, Role.ACCOUNTANT, Role.OWNER]


@login_required
@role_required(PRODUCTION_VIEWERS)
def production_run_list_view(request):
    runs = ProductionRun.objects.select_related('product', 'bom', 'created_by').order_by('-created_at')
    return render(request, 'production/production_run_list.html', {
        'production_runs': runs,
    })


@login_required
@role_required(PRODUCTION_MANAGERS)
def production_run_create_view(request):
    if request.method == 'POST':
        form = ProductionRunCreateForm(request.POST)
        if form.is_valid():
            product = form.cleaned_data['product']
            bom = form.cleaned_data['bom']
            multiplier = form.cleaned_data['batch_multiplier']
            start_date = form.cleaned_data['start_date']
            notes = form.cleaned_data['notes']

            run = create_production_run(
                product=product,
                bom=bom,
                batch_multiplier=multiplier,
                start_date=start_date,
                notes=notes,
                user=request.user,
            )
            messages.success(request, f"Production Run {run.run_number} created as Planned.")
            return redirect('production:production_run_detail', pk=run.pk)
    else:
        form = ProductionRunCreateForm()

    return render(request, 'production/production_run_form.html', {
        'form': form,
        'title': 'Start New Production Run',
    })


@login_required
@role_required(PRODUCTION_VIEWERS)
def production_run_detail_view(request, pk):
    run = get_object_or_404(
        ProductionRun.objects.select_related('product', 'bom', 'created_by').prefetch_related('items__unit', 'items__raw_material', 'items__packaging_item'),
        pk=pk
    )
    raw_material_items = run.items.filter(raw_material__isnull=False)
    packaging_items = run.items.filter(packaging_item__isnull=False)

    can_manage = request.user.role in PRODUCTION_MANAGERS or request.user.is_superuser

    return render(request, 'production/production_run_detail.html', {
        'run': run,
        'raw_material_items': raw_material_items,
        'packaging_items': packaging_items,
        'can_manage': can_manage,
    })


@login_required
@role_required(PRODUCTION_MANAGERS)
def production_run_issue_view(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if run.status != ProductionRun.Status.DRAFT:
        messages.error(request, f"Cannot issue materials for run {run.run_number}: status is {run.get_status_display()}.")
        return redirect('production:production_run_detail', pk=run.pk)

    raw_items = run.items.filter(raw_material__isnull=False).select_related('raw_material', 'unit')

    if request.method == 'POST':
        issues_data = []
        for item in raw_items:
            qty_field = f"qty_{item.id}"
            cost_field = f"cost_{item.id}"
            val = request.POST.get(qty_field)
            cost_val = request.POST.get(cost_field)
            if val is not None:
                d = {'item_id': item.id, 'actual_quantity': Decimal(str(val))}
                if cost_val:
                    d['unit_cost'] = Decimal(str(cost_val))
                issues_data.append(d)

        try:
            movements = issue_materials_for_run(run, issues_data=issues_data, user=request.user)
            messages.success(request, f"Successfully issued materials for {run.run_number}. {len(movements)} stock ledger movements recorded.")
            return redirect('production:production_run_detail', pk=run.pk)
        except Exception as e:
            messages.error(request, f"Error issuing materials: {e}")

    return render(request, 'production/production_run_issue.html', {
        'run': run,
        'raw_items': raw_items,
    })


@login_required
@role_required(PRODUCTION_MANAGERS)
def production_run_output_view(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if run.status != ProductionRun.Status.IN_PROGRESS:
        messages.error(request, f"Cannot record output for run {run.run_number}: status is {run.get_status_display()}.")
        return redirect('production:production_run_detail', pk=run.pk)

    if request.method == 'POST':
        form = ProductionOutputForm(request.POST)
        if form.is_valid():
            actual_yield = form.cleaned_data['actual_yield']
            damaged = form.cleaned_data['damaged_pouches']
            cartons = form.cleaned_data['cartons_used']
            labour = form.cleaned_data['labour_cost'] or Decimal('0.00')
            overhead = form.cleaned_data['overhead_cost'] or Decimal('0.00')
            comp_date = form.cleaned_data['completion_date']

            try:
                movements = record_production_output(
                    run=run,
                    actual_yield=actual_yield,
                    damaged_pouches=damaged,
                    cartons_used=cartons,
                    labour_cost=labour,
                    overhead_cost=overhead,
                    completion_date=comp_date,
                    user=request.user,
                )
                messages.success(request, f"Production Run {run.run_number} completed! {actual_yield} good packets produced. {len(movements)} stock movements recorded.")
                return redirect('production:production_run_detail', pk=run.pk)
            except Exception as e:
                messages.error(request, f"Error completing production run: {e}")
    else:
        carton_pack = run.product.carton_pack_qty or 20
        init_cartons = (run.expected_yield + carton_pack - 1) // carton_pack
        form = ProductionOutputForm(initial={
            'actual_yield': run.expected_yield,
            'damaged_pouches': 0,
            'cartons_used': init_cartons,
            'labour_cost': Decimal('0.00'),
            'overhead_cost': Decimal('0.00'),
        })

    return render(request, 'production/production_run_output.html', {
        'run': run,
        'form': form,
    })
