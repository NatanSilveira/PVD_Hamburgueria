from flask import Flask, render_template, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import time

app = Flask(__name__)

# --- CONFIGURAÇÃO ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///banco_novo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# SENHA DO ADMINISTRADOR
SENHA_ADMIN = "1234"

# --- MODELOS ---
class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    taxa_servico = db.Column(db.Float, default=10.0)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.String(200))

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comanda_id = db.Column(db.Integer, nullable=True)
    produto_nome = db.Column(db.String(100), nullable=False)
    # NOVO: Salvar categoria aqui para filtrar a cozinha
    categoria_item = db.Column(db.String(50), default='Geral') 
    preco = db.Column(db.Float, nullable=False)
    mesa = db.Column(db.Integer, nullable=False)
    cliente_nome = db.Column(db.String(100), default='')
    observacao = db.Column(db.String(200), default='')
    data_hora = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='Carrinho')
    
    # CAMPOS FINANCEIROS
    forma_pagamento = db.Column(db.String(50))
    desconto_aplicado = db.Column(db.Float, default=0.0)
    taxa_cobrada = db.Column(db.Float, default=0.0)

# --- CARGA INICIAL ---
CARDAPIO_PADRAO = [
    {'categoria': '🍔 Hambúrgueres', 'nome': 'X-Dom', 'preco': 25.00, 'desc': 'Pão brioche, carne 160g, queijo prato e maionese da casa'},
    {'categoria': '🍔 Hambúrgueres', 'nome': 'X-Bacon', 'preco': 28.00, 'desc': 'Muito bacon crocante e cheddar cremoso'},
    {'categoria': '🍔 Hambúrgueres', 'nome': 'Smash Duplo', 'preco': 30.00, 'desc': 'Dois burgers prensados na chapa'},
    {'categoria': '🍟 Acompanhamentos', 'nome': 'Batata Frita', 'preco': 15.00, 'desc': 'Porção individual sequinha'},
    {'categoria': '🥤 Bebidas', 'nome': 'Coca-Cola Lata', 'preco': 6.00, 'desc': '350ml gelada'},
    {'categoria': '🥤 Bebidas', 'nome': 'Suco Natural', 'preco': 10.00, 'desc': 'Laranja ou Limão'},
]

with app.app_context():
    db.create_all()
    if Configuracao.query.count() == 0: db.session.add(Configuracao(taxa_servico=10.0))
    if Produto.query.count() == 0:
        for item in CARDAPIO_PADRAO: db.session.add(Produto(nome=item['nome'], preco=item['preco'], categoria=item['categoria'], descricao=item['desc']))
    db.session.commit()

# --- ROTAS GARÇOM ---
@app.route('/')
def index():
    mesa_atual = request.args.get('mesa', 1, type=int)
    manter_carrinho = request.args.get('carrinho_aberto', 0, type=int)
    
    # LÓGICA DO DROPDOWN (Buscar mesas ativas com nomes)
    # Busca IDs de mesas com conta aberta
    mesas_query = db.session.query(Pedido.mesa, Pedido.cliente_nome).filter(Pedido.status != 'Pago').distinct().all()
    
    # Cria um dicionário para evitar duplicatas e pegar o nome mais recente
    dict_mesas = {}
    for m_id, m_nome in mesas_query:
        if m_id not in dict_mesas:
            dict_mesas[m_id] = m_nome
        # Atualiza se tiver nome (caso tenha pego um vazio antes)
        if m_nome: 
            dict_mesas[m_id] = m_nome
            
    # Transforma em lista ordenada para o HTML
    lista_mesas_ativas = []
    for m_id in sorted(dict_mesas.keys()):
        lista_mesas_ativas.append({'id': m_id, 'cliente': dict_mesas[m_id]})

    # Busca pedido atual para preencher nome se existir
    ultimo_pedido = Pedido.query.filter_by(mesa=mesa_atual).filter(Pedido.status != 'Pago').order_by(Pedido.id.desc()).first()
    cliente_atual = ultimo_pedido.cliente_nome if ultimo_pedido else ""
    
    # Cardápio
    produtos_db = Produto.query.all()
    itens_por_categoria = {}
    for p in produtos_db:
        if p.categoria not in itens_por_categoria: itens_por_categoria[p.categoria] = []
        # Passa a categoria junto para o HTML usar no form
        itens_por_categoria[p.categoria].append({'nome': p.nome, 'preco': p.preco, 'desc': p.descricao, 'cat': p.categoria})
    
    categorias_ordenadas = {}
    ordem_preferencia = ['🍔 Hambúrgueres', '🍟 Acompanhamentos', '🥤 Bebidas', '🍰 Sobremesas']
    for cat in ordem_preferencia:
        if cat in itens_por_categoria: categorias_ordenadas[cat] = itens_por_categoria.pop(cat)
    categorias_ordenadas.update(itens_por_categoria)

    carrinho = Pedido.query.filter_by(mesa=mesa_atual, status='Carrinho').all()
    ativos = Pedido.query.filter(Pedido.mesa == mesa_atual, Pedido.status.in_(['Pendente', 'Preparando', 'Pronto', 'Entregue'])).order_by(Pedido.data_hora.desc()).all()
    
    return render_template('cardapio.html', categorias=categorias_ordenadas, mesa=mesa_atual, cliente=cliente_atual, carrinho=carrinho, ativos=ativos, mesas_ativas=lista_mesas_ativas, carrinho_aberto=manter_carrinho)

@app.route('/adicionar_item', methods=['POST'])
def adicionar_item():
    mesa = request.form['mesa']
    cliente = request.form['cliente_nome']
    
    # NOVO: Recebe a categoria do HTML
    cat = request.form.get('categoria_produto', 'Geral')
    
    db.session.add(Pedido(
        mesa=mesa, 
        cliente_nome=cliente, 
        produto_nome=request.form['nome_produto'], 
        categoria_item=cat, # Salva a categoria
        preco=float(request.form['preco']), 
        observacao=request.form['observacao'], 
        status='Carrinho'
    ))
    db.session.commit()
    return redirect(f'/?mesa={mesa}')

@app.route('/enviar_cozinha/<int:mesa>')
def enviar_cozinha(mesa):
    itens = Pedido.query.filter_by(mesa=mesa, status='Carrinho').all()
    if itens:
        id_comanda = int(time.time())
        for item in itens:
            item.comanda_id = id_comanda
            item.data_hora = datetime.now()
            
            # --- FILTRO INTELIGENTE DA COZINHA ---
            # Se for Bebida ou Sobremesa, NÃO vai pra cozinha (status já vira Entregue)
            if 'Bebidas' in item.categoria_item or 'Sobremesas' in item.categoria_item:
                item.status = 'Entregue' 
            else:
                item.status = 'Pendente' # Vai pra cozinha (Hambúrgueres, Acompanhamentos)
                
        db.session.commit()
    return redirect(f'/?mesa={mesa}')

@app.route('/cancelar_item/<int:id>')
def cancelar_item(id):
    item = Pedido.query.get(id)
    if item:
        mesa = item.mesa
        db.session.delete(item)
        db.session.commit()
        return redirect(f'/?mesa={mesa}&carrinho_aberto=1')
    return redirect('/')

@app.route('/garcom_confirma/<int:mesa>')
def garcom_confirma(mesa):
    for item in Pedido.query.filter_by(mesa=mesa, status='Pronto').all():
        item.status = 'Entregue'
    db.session.commit()
    return redirect(f'/?mesa={mesa}')

# --- ROTAS COZINHA (Igual) ---
@app.route('/cozinha')
def cozinha():
    # Cozinha só vê o que é Pendente/Preparando/Pronto. 
    # Como as bebidas já viraram "Entregue" no envio, elas nem aparecem aqui!
    itens = Pedido.query.filter(Pedido.status.in_(['Pendente', 'Preparando', 'Pronto'])).order_by(Pedido.data_hora).all()
    comandas = {}
    for item in itens:
        if item.comanda_id not in comandas:
            comandas[item.comanda_id] = {'id': item.comanda_id, 'mesa': item.mesa, 'cliente': item.cliente_nome, 'hora': item.data_hora.strftime('%H:%M'), 'status': item.status, 'itens': []}
        comandas[item.comanda_id]['itens'].append(item)
    return render_template('cozinha.html', comandas=list(comandas.values()))

@app.route('/iniciar_preparo/<int:comanda_id>')
def iniciar_preparo(comanda_id):
    for item in Pedido.query.filter_by(comanda_id=comanda_id).all():
        if item.status == 'Pendente': item.status = 'Preparando'
    db.session.commit()
    return redirect('/cozinha')

@app.route('/marcar_pronto/<int:comanda_id>')
def marcar_pronto(comanda_id):
    for item in Pedido.query.filter_by(comanda_id=comanda_id).all():
        item.status = 'Pronto'
    db.session.commit()
    return redirect('/cozinha')

@app.route('/finalizar_entrega/<int:comanda_id>')
def finalizar_entrega(comanda_id):
    for item in Pedido.query.filter_by(comanda_id=comanda_id).all():
        item.status = 'Entregue'
    db.session.commit()
    return redirect('/cozinha')

# --- API ---
@app.route('/api/status_mesa/<int:mesa>')
def api_status_mesa(mesa):
    pend = Pedido.query.filter_by(mesa=mesa, status='Pendente').count()
    prep = Pedido.query.filter_by(mesa=mesa, status='Preparando').count()
    pronto = Pedido.query.filter_by(mesa=mesa, status='Pronto').count()
    entregue = Pedido.query.filter_by(mesa=mesa, status='Entregue').count()
    assinatura = f"{pend}-{prep}-{pronto}-{entregue}"
    return jsonify({'assinatura': assinatura, 'tem_pronto': pronto > 0})

@app.route('/api/mesas_prontas')
def api_mesas_prontas():
    mesas = db.session.query(Pedido.mesa).filter_by(status='Pronto').distinct().all()
    lista_mesas = [m[0] for m in mesas]
    return jsonify({'mesas_prontas': lista_mesas})

@app.route('/api/checar_novos_pedidos')
def api_checar():
    pend = Pedido.query.filter_by(status='Pendente').count()
    prep = Pedido.query.filter_by(status='Preparando').count()
    pronto = Pedido.query.filter_by(status='Pronto').count()
    assinatura = f"{pend}-{prep}-{pronto}"
    return jsonify({'assinatura': assinatura, 'som_alert': pend > 0})

@app.route('/api/admin_stats')
def api_admin_stats():
    from sqlalchemy import func
    
    # Conta quantos itens existem em cada status
    pend = Pedido.query.filter_by(status='Pendente').count()
    prep = Pedido.query.filter_by(status='Preparando').count()
    pronto = Pedido.query.filter_by(status='Pronto').count()
    entregue = Pedido.query.filter_by(status='Entregue').count()
    
    # NOVO: Soma o valor total de todos os pedidos ativos.
    # Assim, se entrar uma Coca (que já nasce 'Entregue'), o valor total muda e o admin atualiza.
    total_valor = db.session.query(func.sum(Pedido.preco)).filter(
        Pedido.status.in_(['Pendente', 'Preparando', 'Pronto', 'Entregue'])
    ).scalar() or 0.0
    
    # A assinatura agora inclui o dinheiro. Mudou o dinheiro? Atualiza a tela.
    assinatura = f"{pend}-{prep}-{pronto}-{entregue}-{total_valor}"
    
    return jsonify({'assinatura': assinatura})

# --- ADMIN E FECHAMENTO ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if 'taxa_servico' in request.form:
            conf = Configuracao.query.first()
            conf.taxa_servico = float(request.form['taxa_servico'])
            db.session.commit()
            return redirect('/admin?tab=ajustes')
        
        elif 'nome' in request.form and 'acao' not in request.form:
            db.session.add(Produto(
                nome=request.form['nome'], 
                preco=float(request.form['preco']), 
                categoria=request.form['categoria'], 
                descricao=request.form['descricao']
            ))
            db.session.commit()
            return redirect('/admin?tab=produtos')

        elif 'acao' in request.form and request.form['acao'] == 'editar':
            prod_id = request.form['produto_id']
            prod = Produto.query.get(prod_id)
            if prod:
                prod.nome = request.form['nome']
                prod.preco = float(request.form['preco'])
                prod.categoria = request.form['categoria']
                prod.descricao = request.form['descricao']
                db.session.commit()
            return redirect('/admin?tab=produtos')
    
    produtos = Produto.query.all()
    config = Configuracao.query.first()
    
    pedidos_abertos = Pedido.query.filter(Pedido.status.in_(['Pendente', 'Preparando', 'Pronto', 'Entregue'])).all()
    mesas_abertas = {}
    for p in pedidos_abertos:
        if p.mesa not in mesas_abertas: mesas_abertas[p.mesa] = {'mesa': p.mesa, 'cliente': p.cliente_nome, 'subtotal': 0, 'itens': []}
        mesas_abertas[p.mesa]['subtotal'] += p.preco
        mesas_abertas[p.mesa]['itens'].append(p)
    
    for m in mesas_abertas.values():
        m['taxa_sugerida'] = m['subtotal'] * (config.taxa_servico / 100)
        m['total_estimado'] = m['subtotal'] + m['taxa_sugerida']

    data_filtro_str = request.args.get('data')
    if data_filtro_str:
        data_filtro = datetime.strptime(data_filtro_str, '%Y-%m-%d').date()
    else:
        data_filtro = date.today()

    pedidos_pagos = Pedido.query.filter(
        Pedido.status == 'Pago', 
        Pedido.data_hora >= datetime.combine(data_filtro, datetime.min.time()),
        Pedido.data_hora <= datetime.combine(data_filtro, datetime.max.time())
    ).order_by(Pedido.data_hora.desc()).all()
    
    historico_pagamentos = {}
    faturamento_bruto = 0
    faturamento_taxa = 0

    for p in pedidos_pagos:
        chave = p.comanda_id if p.comanda_id else f"pg_{p.id}"
        if chave not in historico_pagamentos:
            historico_pagamentos[chave] = {
                'id': chave, 'mesa': p.mesa, 'cliente': p.cliente_nome, 'hora': p.data_hora.strftime('%H:%M'), 
                'subtotal': 0, 'desconto': p.desconto_aplicado or 0, 'taxa': p.taxa_cobrada or 0, 
                'pagamento': p.forma_pagamento or 'Dinheiro', 'itens': []
            }
        historico_pagamentos[chave]['itens'].append(p)
        historico_pagamentos[chave]['subtotal'] += p.preco
        
    lista_historico = []
    for recibo in historico_pagamentos.values():
        recibo['total_final'] = recibo['subtotal'] + recibo['taxa'] - recibo['desconto']
        faturamento_bruto += recibo['total_final'] - recibo['taxa']
        faturamento_taxa += recibo['taxa']
        lista_historico.append(recibo)
        
    return render_template('admin.html', produtos=produtos, mesas=mesas_abertas, config=config, historico=lista_historico, total_dia=faturamento_bruto + faturamento_taxa, total_taxa=faturamento_taxa, data_atual=data_filtro, senha_admin=SENHA_ADMIN)

@app.route('/admin/fechar_conta_post', methods=['POST'])
def fechar_conta_post():
    mesa = int(request.form['mesa'])
    
    forma_pagamento = request.form['pagamento']
    desconto = float(request.form['desconto'] or 0)
    cobrar_taxa = 'taxa_servico' in request.form
    
    pedidos = Pedido.query.filter(Pedido.mesa == mesa, Pedido.status.in_(['Pendente', 'Preparando', 'Pronto', 'Entregue'])).all()
    
    if not pedidos: return redirect('/admin?tab=comandas')

    subtotal = sum(p.preco for p in pedidos)
    config = Configuracao.query.first()
    taxa_valor = (subtotal * (config.taxa_servico / 100)) if cobrar_taxa else 0.0
    
    qtd_itens = len(pedidos)
    agora = datetime.now()
    
    for p in pedidos:
        p.status = 'Pago'
        p.data_hora = agora
        p.forma_pagamento = forma_pagamento
        p.desconto_aplicado = desconto / qtd_itens
        p.taxa_cobrada = taxa_valor / qtd_itens
        
    db.session.commit()
    return redirect('/admin?tab=comandas')

@app.route('/admin/deletar/<int:id>')
def admin_deletar(id):
    prod = Produto.query.get(id)
    if prod: db.session.delete(prod); db.session.commit()
    return redirect('/admin?tab=produtos')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')