VERSION 5.00
Object = "{83B0E423-D4EE-11D4-BEDF-BAB7F1EEA455}#4.2#0"; "addflow4.ocx"
Object = "{C048E7C2-514E-11D5-9781-0002E30447DE}#3.0#0"; "prnflow3.ocx"
Begin VB.Form frmFlow 
   Caption         =   "Form1"
   ClientHeight    =   3945
   ClientLeft      =   3315
   ClientTop       =   2685
   ClientWidth     =   5160
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   Icon            =   "frmFlow.frx":0000
   LinkTopic       =   "Form1"
   ScaleHeight     =   263
   ScaleMode       =   3  'Pixel
   ScaleWidth      =   344
   StartUpPosition =   3  'Windows Default
   Begin AddFlow4Lib.AddFlow FlowGUI 
      Height          =   3135
      Left            =   120
      TabIndex        =   0
      Top             =   0
      Width           =   4455
      _Version        =   262146
      _ExtentX        =   7858
      _ExtentY        =   5530
      _StockProps     =   229
      BackColor       =   16777215
      BeginProperty Font {0BE35203-8F91-11CE-9DE3-00AA004BB851} 
         Name            =   "Arial"
         Size            =   8.25
         Charset         =   0
         Weight          =   400
         Underline       =   0   'False
         Italic          =   0   'False
         Strikethrough   =   0   'False
      EndProperty
      BorderStyle     =   0
      ScrollBars      =   3
      Shape           =   1
      LinkStyle       =   0
      Alignment       =   7
      AutoSize        =   0
      ArrowDst        =   3
      ArrowOrg        =   0
      DrawStyle       =   0
      DrawWidth       =   1
      ReadOnly        =   0   'False
      MultiSel        =   -1  'True
      CanDrawNode     =   0   'False
      CanDrawLink     =   -1  'True
      CanMoveNode     =   -1  'True
      CanSizeNode     =   -1  'True
      CanStretchLink  =   -1  'True
      CanMultiLink    =   -1  'True
      Transparent     =   0   'False
      ShowGrid        =   -1  'True
      Hidden          =   0   'False
      Rigid           =   0   'False
      DisplayHandles  =   -1  'True
      AutoScroll      =   -1  'True
      xGrid           =   8
      yGrid           =   8
      xZoom           =   100
      yZoom           =   100
      FillColor       =   16777215
      DrawColor       =   0
      ForeColor       =   0
      BackPicture     =   "frmFlow.frx":0E42
      MouseIcon       =   "frmFlow.frx":0E5E
      AdjustOrg       =   0   'False
      AdjustDst       =   -1  'True
      CanReflexLink   =   -1  'True
      SnapToGrid      =   -1  'True
      ShowToolTip     =   -1  'True
      ScrollTrack     =   -1  'True
      AllowArrowKeys  =   -1  'True
      ProportionalBars=   -1  'True
      PicturePosition =   9
      LinkCreationMode=   0
      GridStyle       =   0
      ShapeOrientation=   0
      ArrowMid        =   0
      SelectAction    =   0
      GridColor       =   0
      OrthogonalDynamic=   -1  'True
      OrientedText    =   0   'False
      EditMode        =   0
      Shadow          =   0
      ShadowColor     =   0
      BackMode        =   2
      Ellipsis        =   0
      SelectionHandleSize=   6
      LinkingHandleSize=   12
      xShadowOffset   =   8
      yShadowOffset   =   8
      CanUndoRedo     =   -1  'True
      UndoSize        =   0
      ShowPropertyPages=   0
      NoPrefix        =   0   'False
      MaxInDegree     =   -1
      MaxOutDegree    =   -1
      MaxDegree       =   -1
      CycleMode       =   0
      LogicalOnly     =   0   'False
      ShowJump        =   1
      SizeArrowDst    =   1
      SizeArrowOrg    =   1
      SizeArrowMid    =   0
      ScrollWheel     =   -1  'True
      RemovePointAngle=   2
      ZeroOriginForExport=   0   'False
      CanFireError    =   0   'False
   End
   Begin PrnFlow3Lib.PrnFlow prn 
      Height          =   735
      Left            =   2580
      TabIndex        =   1
      Top             =   3000
      Visible         =   0   'False
      Width           =   1515
      _Version        =   196608
      _ExtentX        =   2672
      _ExtentY        =   1296
      _StockProps     =   45
      BeginProperty Font {0BE35203-8F91-11CE-9DE3-00AA004BB851} 
         Name            =   "Arial"
         Size            =   8.25
         Charset         =   0
         Weight          =   400
         Underline       =   0   'False
         Italic          =   0   'False
         Strikethrough   =   0   'False
      EndProperty
      BorderStyle     =   1
      PageBorder      =   0
      Preview         =   0   'False
      PrinterSettings =   0   'False
      MousePage       =   -1  'True
      MarginLeft      =   1440
      MarginTop       =   1440
      MarginRight     =   1440
      MarginBottom    =   1440
      MarginHeader    =   0
      MarginFooter    =   0
      Header          =   ""
      Footer          =   "|<PAGE>|"
      DocName         =   ""
      MouseZoom       =   -1  'True
      Zoom            =   0
      Orientation     =   1
      FitToPage       =   0   'False
   End
End
Attribute VB_Name = "frmFlow"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private Const mcstrModule = "frmFlow"
'// if true then a save will cause an overwrite. some features also disabled in the designer
Private mForUpdate As Boolean
Private moVersions As Versions
Private moParent As Container
Public mProcessDef As ProcessDef
Public mProcessVersion As ProcessVersion
'/ last XY pos of mouse - used for pasting
Private msglLastX As Single
Private msglLastY As Single
Private WithEvents moPropList As frmPropList
Attribute moPropList.VB_VarHelpID = -1
Implements IContextMenu
Private moSettings As ProcessTemplate
Private moTaskTemplates As TaskTemplates
Private moProcessTemplates As ProcessTemplates
Private mstrFileName As String

Public Sub init(oParent As Container, oProcessTemplate As ProcessTemplate, oTaskTemplates As TaskTemplates, oProcessTemplates As ProcessTemplates)
    Set moParent = oParent
    Set mProcessDef = New ProcessDef
    '/ dont both with this any more
    ' mProcessDef.Guid = CreateGUID
    
    FlowGUI.SelectMode = True
    Set moSettings = oProcessTemplate
    Set moTaskTemplates = oTaskTemplates
    Set moProcessTemplates = oProcessTemplates
End Sub

Public Sub NewFlow()
    Dim oProp As Property
    Dim oNewProp As Property
    mProcessDef.ProcessTemplate = moSettings.Name
    Dim oProps As Properties
    CopyPropGroup moSettings.ProcessProperties, mProcessDef.PropertyGroup
    mProcessDef.Name = "New " & moProcessTemplates(mProcessDef.ProcessTemplate).Name
End Sub

Private Property Get Parent() As frmMDI
    Set Parent = moParent.getParent
End Property

Private Sub FlowGUI_AfterAddLink(ByVal NewLink As AddFlow4Lib.afLink)
    Dim oRouting As RoutingDef
    Dim oOrgTaskDef As TaskDef
    Set oOrgTaskDef = mProcessDef.Tasks(NewLink.Org.key)
    Set oRouting = mProcessDef.Routings.Add(oOrgTaskDef, mProcessDef.Tasks(NewLink.Dst.key))
    CopyPropGroup moSettings.CommonRoutingProperties, oRouting.PropertyGroup, False, True, False
    
    '# just in case the task template cannot be found - this can happen!
    On Error Resume Next
    oRouting.Parallel = moTaskTemplates(oOrgTaskDef.TaskTemplate).RoutingParallel
    '# this setting also overrides anything specified in common properties... as it should do
    On Error GoTo 0
    
    NewLink.key = oRouting.Guid
    AlignClosestEdge NewLink
    Call Sanitize
End Sub

Private Sub FlowGUI_AfterMove()
    '# update node and link position info
    Dim oNode As afNode
    For Each oNode In FlowGUI.SelNodes
        NodeMoved oNode
    Next
End Sub

Private Sub NodeMoved(oNode As afNode)
    Dim oTaskDef As TaskDef
    Set oTaskDef = mProcessDef.Tasks(oNode.key)
    oTaskDef.Left = oNode.Left
    oTaskDef.Top = oNode.Top
    oTaskDef.Width = oNode.Width
    oTaskDef.Height = oNode.Height
    Dim oRouting As RoutingDef
    Dim oPT As afLinkPoint
    Dim oLink As afLink
    
    Dim strKey As String
    Dim lngCount As Long
    
    For Each oRouting In oTaskDef.RoutingIn
        oRouting.ClearPoints
        Set oLink = oNode.InLinks(oRouting.Guid)
        For Each oPT In oLink.ExtraPoints
            If Not IgnorePoint(oLink, oPT) Then
                oRouting.AddPoint oPT.X, oPT.y
            End If
        Next
    Next
    
    For Each oRouting In oTaskDef.RoutingOut
        oRouting.ClearPoints
        Set oLink = oNode.OutLinks(oRouting.Guid)
        For Each oPT In oLink.ExtraPoints
            If Not IgnorePoint(oLink, oPT) Then
                oRouting.AddPoint oPT.X, oPT.y
            End If
        Next
    Next
End Sub

Private Sub FlowGUI_AfterResize()
    NodeMoved FlowGUI.SelectedNode
End Sub

'/ aligns the link destination with the closest edge of the node

Private Sub AlignClosestEdge(oLink As afLink)
    Dim oPT As afLinkPoint
    Dim oNode As afNode
    
    Set oPT = oLink.ExtraPoints.Item(oLink.ExtraPoints.Count - 1)
    Set oNode = oLink.Dst
    
    Dim sglL As Single, sglT As Single
    Dim sglR As Single, sglB As Single
    
    sglL = oPT.X - oNode.Left
    sglR = (oNode.Left + oNode.Width) - oPT.X
    sglT = oPT.y - oNode.Top
    sglB = (oNode.Top + oNode.Height) - oPT.y
    If sglL < sglR And sglL < sglT And sglL < sglB Then
        oPT.X = oPT.X - sglL
    ElseIf sglR < sglL And sglR < sglT And sglR < sglB Then
        oPT.X = oPT.X + sglR
    ElseIf sglB < sglL And sglB < sglR And sglB < sglT Then
        oPT.y = oPT.y + sglB
    Else
        oPT.y = oPT.y - sglT
    End If
    Set oLink.ExtraPoints.Item(oLink.ExtraPoints.Count - 1) = oPT
    
End Sub
Private Function IntersectNodeLine(oTaskDef As TaskDef, X1 As Single, Y1 As Single, X2 As Single, Y2 As Single, ByRef IntersectX As Single, ByRef IntersectY As Single) As Boolean
    IntersectNodeLine = IntersectBoxLine(oTaskDef.Left, oTaskDef.Top, oTaskDef.Width, oTaskDef.Height, X1, Y1, X2, Y2, IntersectX, IntersectY)
End Function
Private Sub FlowGUI_AfterStretch()
    '# occurs whenever a routing point is changed
    Dim oRouting As RoutingDef
    Dim oLink As afLink
    Dim oPT As afLinkPoint
    Dim oTaskDefDest As TaskDef
    Dim fCancel As Integer
    Dim sglX As Single
    Dim sglY As Single
    Dim oNewRouting As RoutingDef
    Dim oProp As Property
    Dim oNewProp As Property
    Set oLink = FlowGUI.SelectedLink
    
    Set oPT = oLink.ExtraPoints(oLink.ExtraPoints.Count - 1)
    Set oTaskDefDest = mProcessDef.Tasks(oLink.Dst.key)
    Set oRouting = mProcessDef.Routings(oLink.key)
    '# check to see if the final point intersects a part of the destination task
    If Not IntersectNodeLine(oTaskDefDest, oLink.ExtraPoints(oLink.ExtraPoints.Count - 1).X, oLink.ExtraPoints(oLink.ExtraPoints.Count - 1).y, oLink.ExtraPoints(oLink.ExtraPoints.Count - 2).X, oLink.ExtraPoints(oLink.ExtraPoints.Count - 2).y, sglX, sglY) Then
        fCancel = True
    ElseIf oRouting.TaskDest.Guid <> oTaskDefDest.Guid Then
        '# change destination
        mProcessDef.Routings.Remove oRouting.Guid
        Set oNewRouting = mProcessDef.Routings.Add(mProcessDef.Tasks(oLink.Org.key), oTaskDefDest, oRouting.Guid)
        
        CopyPropGroup oRouting.PropertyGroup, oNewRouting.PropertyGroup, False, True
    End If
    
    If fCancel Then
        '# dest was invalid for whatever reason
        '# reset the link back to our record of it's points
        
        '# remove from the UI
        oLink.Dst.InLinks.Remove oLink.key
        
        '# redraw the original link
        AddGUIRouting oRouting
        Sanitize
        Exit Sub
    End If
    oRouting.ClearPoints
    
    AlignClosestEdge oLink
    
    For Each oPT In oLink.ExtraPoints
        If Not IgnorePoint(oLink, oPT) Then
            oRouting.AddPoint oPT.X, oPT.y
        End If
    Next
    oLink.ZOrderIndex = 0
    Sanitize
End Sub

Private Sub FlowGUI_Click()
    Call ShowPropWin
End Sub

Private Sub FlowGUI_DblClick()
    Dim strText As String
    Dim oTaskDef As TaskDef
    Dim oRouting As RoutingDef
    If Not (FlowGUI.SelectedNode Is Nothing) Then
        Set oTaskDef = mProcessDef.Tasks(FlowGUI.SelectedNode.key)
        strText = oTaskDef.Name
        If frmInput.ShowInput("Enter the Task Name", strText) Then
            oTaskDef.Name = strText
            FlowGUI.SelectedNode.Text = NodeCaption(oTaskDef)
        End If
        Unload frmInput
        Call Sanitize
    ElseIf Not (FlowGUI.SelectedLink Is Nothing) Then
        strText = FlowGUI.SelectedLink.Text
        If frmInput.ShowInput("Enter the Routing Name", strText) Then
            FlowGUI.SelectedLink.Text = strText
            Set oRouting = mProcessDef.Routings(FlowGUI.SelectedLink.key)
            oRouting.Name = strText
        End If
        Unload frmInput
        Call Sanitize
    End If
    
    
End Sub

Private Function NodeCaption(oTaskDef As TaskDef) As String
    Dim strRtn As String
    Dim oProps As Properties
    Dim oProp As Property
    
    For Each oProp In moSettings.GUITaskDisplay
        For Each oProps In oTaskDef.PropertyGroup
            If oProps.Exists(oProp.Name) Then
                If Len(oProps(oProp.Name).Value) > 0 Then
                    strRtn = strRtn & oProp.Value & oProps(oProp.Name).Value & vbCrLf
                    Exit For
                End If
            End If
        Next
    Next
    If Len(strRtn) > 0 Then
        strRtn = Left$(strRtn, Len(strRtn) - 2)
    Else
        strRtn = oTaskDef.Name
    End If
    NodeCaption = strRtn
End Function

Private Sub FlowGUI_DragDrop(Source As Control, X As Single, y As Single)
    Const cstrFunc = "flow_DragDrop"
    On Error GoTo err_handler
    Dim oNode As AddFlow4Lib.afNode
    Dim oTaskDef As TaskDef
    Dim oTaskTemplate As TaskTemplate
    Set oTaskTemplate = moTaskTemplates(Source.Tag)
    
    Set oTaskDef = mProcessDef.Tasks.Add()
    oTaskDef.Name = Source.Tag
    oTaskDef.TaskTemplate = oTaskTemplate.Name
    
    DoTaskProps oTaskDef, oTaskTemplate
    
    Set oNode = FlowGUI.Nodes.Add(X + FlowGUI.xScroll, y + FlowGUI.yScroll, Source.Width, Source.Height * 2)
    
    Set oNode.Picture = Source.Picture
    
    oNode.xTextMargin = 4
    oNode.yTextMargin = 4
    oNode.Text = NodeCaption(oTaskDef)
    oNode.key = oTaskDef.Guid
    With oTaskDef
        .Left = oNode.Left
        .Top = oNode.Top
        .Width = oNode.Width
        .Height = oNode.Height
    End With
    Set FlowGUI.SelectedNode = oNode
    Call Sanitize
    Call ShowPropWin
    FlowGUI.SetFocus
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub DoTaskProps(oTaskDef As TaskDef, oTaskTemplate As TaskTemplate)
    Debug.Print "Setting TaskTemplate", oTaskTemplate.Name
    CopyPropGroup oTaskTemplate.PropertyGroup, oTaskDef.PropertyGroup, False, True, False
    '# common settings from the process template override task template settings
    Debug.Print "Setting TaskCommonProps", oTaskTemplate.Name
    CopyPropGroup moSettings.CommonTaskProperties, oTaskDef.PropertyGroup, False, True, False
End Sub
Private Sub FlowGUI_KeyUp(KeyCode As Integer, Shift As Integer)
    Const cstrFunc As String = "FlowGUI_KeyUp"
    On Error GoTo err_handler
    If KeyCode = vbKeyDelete Then
        DeleteSelected
    End If
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select

End Sub

Private Sub FlowGUI_MouseDown(Button As Integer, Shift As Integer, X As Single, y As Single)
    Dim oNode As afNode
    Dim oLink As afLink
    Dim oNodeCheck As afNode
    Dim oLinkCheck As afLink
    
    Dim fNoChange As Boolean
    
    If Button = vbRightButton Then
        Set oNode = FlowGUI.GetNodeAtPoint(FlowGUI.xScroll + X, FlowGUI.yScroll + y)
        If oNode Is Nothing Then
            Set oLink = FlowGUI.GetLinkAtPoint(FlowGUI.xScroll + X, FlowGUI.yScroll + y)
            If oLink Is Nothing Then Exit Sub
            For Each oLinkCheck In FlowGUI.SelLinks
                If oLinkCheck.key = oLink.key Then
                    fNoChange = True
                    Exit For
                End If
            Next
            If Not fNoChange Then
                Set FlowGUI.SelectedLink = oLink
            End If
        Else
            For Each oNodeCheck In FlowGUI.SelNodes
                If oNode.key = oNodeCheck.key Then
                    fNoChange = True
                    Exit For
                End If
            Next
            If Not fNoChange Then
                Set FlowGUI.SelectedNode = oNode
            End If
        End If
    End If
End Sub

Private Sub FlowGUI_MouseUp(Button As Integer, Shift As Integer, X As Single, y As Single)
    Dim ods As DockStudio
    Set ods = Parent.ds
    If Button = vbRightButton Then
        If FlowGUI.SelNodes.Count > 0 Then
            ods.Commands.GetPopupMenu("mnuNode").ShowPopup
        ElseIf FlowGUI.SelLinks.Count > 0 Then
            Dim oRouting As RoutingDef
            Set oRouting = mProcessDef.Routings(FlowGUI.SelectedLink.key)
            ods.Commands.GetToolButton("tlParallel").State = IIf(oRouting.Parallel, dsxpCommandToolButtonStateChecked, dsxpCommandToolButtonStateUnchecked)
            ods.Commands.GetPopupMenu("mnuLink").ShowPopup
        Else
            ods.Commands.GetPopupMenu("mnuFlow").ShowPopup
        End If
    End If
    msglLastX = X
    msglLastY = y
End Sub


Private Sub Form_Resize()
    On Error Resume Next
    FlowGUI.Move 0, 0, ScaleWidth, ScaleHeight
End Sub

Private Sub Sanitize()
    '/ check all nodes and put in colour corrections for start/end steps
    Dim oNode As AddFlow4Lib.afNode
    Dim oLink As AddFlow4Lib.afLink
    Dim oTaskDef As TaskDef
    Dim oRouting As RoutingDef
    Dim fGotEnd As Boolean
    Dim fGotStart As Boolean
    
    mProcessDef.isValid = True
    
    Set mProcessDef.FirstTask = Nothing
    
    For Each oNode In FlowGUI.Nodes
        Set oTaskDef = mProcessDef.Tasks(oNode.key)
        oNode.DrawStyle = afInsideSolid
        
        If oNode.OutLinks.Count = 0 Then
            If oNode.InLinks.Count = 0 Then
                '# node with no in or out links
                oNode.DrawColor = vbMagenta 'RGB(&HCC, &HCC, 0)
                mProcessDef.isValid = False
                oNode.DrawWidth = 4
            Else
                '# end node
                oNode.DrawColor = RGB(&HCC, 0, 0)
                oNode.DrawWidth = 4
                fGotEnd = True
            End If
        ElseIf oNode.InLinks.Count = 0 Then
            '# start node
            oNode.DrawWidth = 4
            oNode.DrawColor = RGB(0, &HCC, 0)
            Set mProcessDef.FirstTask = oTaskDef
            fGotStart = True
        Else
            oNode.DrawWidth = 2
            If oTaskDef.Synchronise Then
                oNode.DrawColor = RGB(&HCC, &HCC, 0)
            ElseIf ParallelTask(oTaskDef) Then
                '# task can be run parallel
                oNode.DrawColor = RGB(0, &HAA, &HFF)
            Else
                '# normal node
                oNode.DrawColor = RGB(0, 0, 0)
            End If
            
        End If
        
        SanitizeRouting oNode
        
    Next
    If Not (fGotEnd And fGotStart) Then
        mProcessDef.isValid = False
    End If
    
End Sub

'/ returns true if the TaskDef is kicked off on a parallel route at any stage in the Process
Private Function ParallelTask(oTaskDef As TaskDef) As Boolean
    '# traverse the tasks inbound routings looking for parallels
    
    
    '# collection to hold Tasks we've already visited
    Dim oVisited As Properties
    
    '# to hold list of tasks we need to check
    Dim oCheckTasks As Properties
    
    Dim oRouting As RoutingDef
    Dim oR2 As RoutingDef
    Dim oCheckTask As TaskDef
    Dim oPG As PropertyGroup
    Set oPG = New PropertyGroup
    
    Set oCheckTasks = oPG.Add("CheckTasks")
    Set oVisited = oPG.Add("Visited")
    
    oCheckTasks.Add oTaskDef.Guid, oTaskDef
    
    Do Until oCheckTasks.Count = 0
        Set oCheckTask = oCheckTasks(1).Value
        oCheckTasks.Remove 1
        If oCheckTask.Synchronise Then
            '# task is a sychroniser, so only one thread of execution comes out of it
            '# TODO: however there should be another check to ensure that all parallel routes from a "split" are synchronised by this task
            ParallelTask = False
            Exit Function
        End If
        
        oVisited.Add oCheckTask.Guid, oCheckTask
        
        For Each oRouting In oCheckTask.RoutingIn
            If oRouting.Parallel Then
                '# found a parallel routing
                ParallelTask = True
                Exit Function
            End If
            If Not oVisited.Exists(oRouting.TaskOrg.Guid) Then
                '# check outbound routings from the org task for parallels
                For Each oR2 In oRouting.TaskOrg.RoutingOut
                    If oR2.Parallel Then
                        ParallelTask = True
                        Exit Function
                    End If
                Next
                If Not oCheckTasks.Exists(oRouting.TaskOrg.Guid) Then
                    oCheckTasks.Add oRouting.TaskOrg.Guid, oRouting.TaskOrg
                End If
            End If
        Next
        
    Loop
End Function

'/ checks the validity of a routings from a node
Private Sub SanitizeRouting(oNode As afNode)
    Dim colParallel As Collection
    Dim colSynchronous As Collection
    Dim oLink As afLink
    Dim oRouting As RoutingDef
    
    Set colParallel = New Collection
    Set colSynchronous = New Collection
    
    For Each oLink In oNode.OutLinks
        Set oRouting = mProcessDef.Routings(oLink.key)
        If oRouting.Parallel Then
            colParallel.Add oRouting, oRouting.Guid
        Else
            colSynchronous.Add oRouting, oRouting.Guid
        End If
    Next
    '# for Synchronous routings each must have a name set
    For Each oRouting In colSynchronous
        Set oLink = oNode.OutLinks(oRouting.Guid)
        oLink.DrawWidth = 1
          
          
        '# set to default... black
        oLink.DrawColor = vbBlack
        oLink.ToolTip = vbNullString
        oLink.ArrowOrg = afNoArrow
        oLink.ArrowDst = afFilledArrow30
        oLink.DrawStyle = afSolid
        oLink.ToolTip = vbNullString
        '# check for parallel
        
        If ParallelTask(oRouting.TaskOrg) Or colParallel.Count > 0 Then
            oLink.DrawColor = RGB(0, &HAA, &HFF)
        End If
        
        If Len(oRouting.Name) = 0 Then
            If colSynchronous.Count > 1 Then
                '# make it... mauve...
                oLink.DrawColor = vbMagenta
                oLink.ToolTip = "Routing must be named"
            ElseIf colSynchronous.Count = 1 And oRouting.TaskDest.Guid = oRouting.TaskOrg.Guid Then
                oLink.DrawColor = vbMagenta
                oLink.ToolTip = "Must have multiple outbound Routings to allow a Task to link to itself"
            End If
            
        ElseIf Len(oRouting.PropertyGroup("(General)").Item("Condition Class").Value) = 0 And colSynchronous.Count > 1 Then
                oLink.DrawColor = vbMagenta
                oLink.ToolTip = "Class Name for Routing is not set"
        End If
        
    Next
    
    
        
    
    '# for Parallel routings we just need to adjust the colour
    For Each oRouting In colParallel
        Set oLink = oNode.OutLinks(oRouting.Guid)
        oLink.DrawWidth = 1
        oLink.ToolTip = vbNullString
        oLink.ArrowOrg = afEmptyCircle
        oLink.ArrowDst = afFilledArrow30
        
        If oRouting.TaskDest.Guid = oRouting.TaskOrg.Guid And Len(oRouting.Name) = 0 Then
            oLink.DrawColor = vbMagenta
            oLink.ToolTip = "Routing must have a condition to prevent the Task running an infinite number of times"
        Else
            oLink.DrawColor = RGB(0, &HAA, &HFF)
        End If
        
        
    Next
End Sub
Private Sub IContextMenu_Activate()
    
    Parent.ds.Commands.Item("tlDeleteVersion").Enabled = mForUpdate
    ShowPropWin
End Sub

Private Function IContextMenu_CommandClick(ByVal Command As InnovaDSXP.Command) As Boolean
    On Error GoTo Err_Raise
    
    Select Case UCase$(Command.Name)
        Case "TLDELETE"
            
            IContextMenu_CommandClick = DeleteSelected
            ShowPropWin
        Case "TLDELETEVERSION"
            IContextMenu_CommandClick = True
            Call DeleteVersion
        Case "TLDOCUMENT"
            IContextMenu_CommandClick = True
            Call documentProcess
        Case "TLCOPY"
            IContextMenu_CommandClick = CopySelected
            ShowPropWin
        Case "TLPASTE"
            IContextMenu_CommandClick = Paste
            ShowPropWin
        Case "TLEXPORTIMAGE"
            IContextMenu_CommandClick = True
            Call ExportImage
        Case "TLSAVE"
            IContextMenu_CommandClick = True
            Call SaveFlow(False)
        Case "TLSAVEAS"
            IContextMenu_CommandClick = True
            Call SaveFlow(True)
        Case "TLPRINT"
            IContextMenu_CommandClick = True
            Call PrintFlow
        Case "TLFIND"
            IContextMenu_CommandClick = True
            Call FindData
        Case "TLSPELLCHECK"
            IContextMenu_CommandClick = True
            Call SpellCheck
            ShowPropWin
        Case "TLPARALLEL"
            IContextMenu_CommandClick = True
            Call ToggleParallel
            ShowPropWin
            
        Case "TLRESET"
            IContextMenu_CommandClick = True
            Call ResetToTemplate
            ShowPropWin
        Case "TLPROPERTYREMOVE"
            IContextMenu_CommandClick = True
            If removeProp() Then
                FlowGUI.SetChangedFlag True
                ShowPropWin
            End If
        Case "TLCHANGETASKTYPE"
            IContextMenu_CommandClick = True
            changeTaskType
    End Select
    Exit Function
Err_Raise:
    Call ErrRaise(Err, mcstrModule, "IContextMenu_CommandClick")
    
End Function
Private Sub changeTaskType()
    If Not Parent.changeTaskType(mProcessDef.Tasks(FlowGUI.SelectedNode.key)) Then
        Exit Sub
    End If
    FlowGUI.SetChangedFlag True
    Dim nde As afNode
    Set nde = FlowGUI.SelectedNode
    Set nde.Picture = LoadPicture(App.Path & mcstrImagesPath & moTaskTemplates(mProcessDef.Tasks(nde.key).TaskTemplate).Icon)
    IContextMenu_Refresh
End Sub
Private Sub documentProcess()
    Const cstrFunc = "documentProcess"
    Dim strErrFunc As String
    
    Dim dlg As MSComDlg.CommonDialog
    
    Set dlg = Parent.dlg
    dlg.Filter = "HTML Documents|*.html"
    dlg.FilterIndex = 1
    dlg.DialogTitle = "Document Process"
    dlg.fileName = mProcessDef.Name
    dlg.Flags = MSComDlg.cdlOFNOverwritePrompt
    On Error Resume Next
    dlg.ShowSave
    If Err.Number <> 0 Then Exit Sub
    On Error GoTo err_handler
    strErrFunc = "Deleting existing file"
    If Len(Dir$(dlg.fileName)) > 0 Then
        Kill dlg.fileName
    End If
    
    strErrFunc = "Creating documentation"
    Dim oDocProcess As DocFlow
    Set oDocProcess = New DocFlow
    oDocProcess.DocProcess mProcessDef, dlg.fileName, False
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc, strErrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub
Private Sub DeleteVersion()
    '// check that the user really wants to do this
    If MsgBox("Are you SURE you want to DELETE this Version? This operation cannot be undone and will automatically save the current Process Definition.", vbCritical Or vbDefaultButton2 Or vbOKCancel, "Delete Version") = vbCancel Then
        Exit Sub
    End If
    '// save the whole shebang
    Dim oExport As XMLProcessVersion
    Set oExport = New XMLProcessVersion
    oExport.FileDeleteVersion mstrFileName, mProcessVersion
    '// mark flow as unchanged
    FlowGUI.SetChangedFlag False
    '// ...so that we can close this window without an error message
    Parent.ds.ActiveDocumentWindow.Delete
    Unload Me
End Sub
    
Public Property Get canRemoveProp(oProp As Property) As Boolean
    canRemoveProp = False
    
    If oProp Is Nothing Then
        Exit Function
    End If
    
    '/ see which template we need to look at - process/task/routing
    Dim oProcessTemplate As ProcessTemplate
    Set oProcessTemplate = moProcessTemplates(mProcessDef.ProcessTemplate)
    
    If FlowGUI.SelectedNode Is Nothing And FlowGUI.SelectedLink Is Nothing Then
        '/ process
        canRemoveProp = Not propExists(oProp, oProcessTemplate.ProcessProperties)
            If canRemoveProp Then
                If oProp.Properties.Name = "(General)" Then
                    Select Case LCase$(oProp.Name)
                        Case "name"
                            canRemoveProp = False
                    End Select
                End If
            End If
        ElseIf FlowGUI.SelectedLink Is Nothing Then
        '/ task
        canRemoveProp = Not propExists(oProp, oProcessTemplate.CommonTaskProperties)
        If canRemoveProp Then
            canRemoveProp = Not propExists(oProp, moTaskTemplates.Item(mProcessDef.Tasks(FlowGUI.SelectedNode.key).TaskTemplate).PropertyGroup)
        End If
        If canRemoveProp Then
            If oProp.Properties.Name = "(General)" Then
                Select Case LCase$(oProp.Name)
                    Case "class name", "synchronise", "name", "auto", "newthread"
                        canRemoveProp = False
                End Select
            End If
        End If
    Else
        '/ routing
        canRemoveProp = Not propExists(oProp, oProcessTemplate.CommonRoutingProperties)
        If canRemoveProp Then
            If oProp.Properties.Name = "(General)" Then
                Select Case LCase$(oProp.Name)
                    Case "condition class", "parallel", "name"
                        canRemoveProp = False
                End Select
            End If
        End If
    End If
    
End Property
Private Function propExists(oProp As ACGProperties.Property, oPropGroup As PropertyGroup) As Boolean
    '/ check to see prop group exists
    propExists = False
    If Not oPropGroup.Exists(oProp.Properties.Name) Then
        Exit Function
    End If
    '/ check to see if the property is in properties list
    propExists = oPropGroup.Item(oProp.Properties.Name).Exists(oProp.Name)
End Function
Private Function removeProp() As Boolean
    Dim oProp As Property
    Set oProp = moPropList.pg.Selected
    
    If MsgBox("Are you sure you want to remove property """ + oProp.Name + """?", vbYesNo + vbQuestion) = vbNo Then
        Exit Function
    End If
    
    '/ remove it
    oProp.Properties.Remove oProp.Name
    removeProp = True
End Function
'/ resets the currently select item (flow, task or routing) back to the template specified default
Private Sub ResetToTemplate()
    Const cstrFunc = "ResetToTemplate"
    On Error GoTo err_handler
    
    If MsgBox("Are you SURE you want to reset the selected items to their template-supplied default values?", vbYesNo + vbDefaultButton2) = vbNo Then Exit Sub
    Dim oNode As afNode
    Dim oTask As TaskDef
    Dim oProcessTemplate As ProcessTemplate
    Set oProcessTemplate = moProcessTemplates(mProcessDef.ProcessTemplate)
    For Each oNode In FlowGUI.SelNodes
        Set oTask = mProcessDef.Tasks(oNode.key)
        CopyPropGroup oProcessTemplate.CommonTaskProperties, oTask.PropertyGroup, False, True, True
        CopyPropGroup moTaskTemplates(oTask.TaskTemplate).PropertyGroup, oTask.PropertyGroup, False, True, True
    Next
    Dim oLink As afLink
    Dim oRouting As RoutingDef
    For Each oLink In FlowGUI.SelLinks
        Set oRouting = mProcessDef.Routings(oLink.key)
        CopyPropGroup oProcessTemplate.CommonRoutingProperties, oRouting.PropertyGroup, False, True, True
    Next
    If (FlowGUI.SelLinks.Count = 0 And FlowGUI.SelNodes.Count = 0) Then
        CopyPropGroup oProcessTemplate.ProcessProperties, mProcessDef.PropertyGroup, False, True, True
    End If
    Call Sanitize
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub
Private Sub ToggleParallel()
    Dim oRouting As RoutingDef
    Set oRouting = mProcessDef.Routings(FlowGUI.SelectedLink.key)
    If oRouting.PropertyGroup("(General)").Item("Parallel").Locked Then
        MsgBox "Cannot change this property", vbInformation
    Else
        oRouting.Parallel = Not oRouting.Parallel
        
        Call Sanitize
    End If
    
End Sub

'/ deletes selected steps / routing
Private Function DeleteSelected() As Boolean
    Dim oTaskDef As TaskDef
    Dim oRouting As RoutingDef
    Dim colRemoveRouting As Collection
    Set colRemoveRouting = New Collection
    Dim oNode As afNode
    Dim oLink As afLink
    On Error Resume Next
    For Each oNode In FlowGUI.SelNodes
        For Each oLink In oNode.OutLinks
            colRemoveRouting.Add oLink.key, oLink.key
        Next
        For Each oLink In oNode.InLinks
            colRemoveRouting.Add oLink.key, oLink.key
        Next
    Next
    '# can get an error here as the link may already be selected for deletion
    
    For Each oLink In FlowGUI.SelLinks
        colRemoveRouting.Add oLink.key, oLink.key
    Next
    On Error GoTo Err_Raise
    
    '# remove all routings
    Do Until colRemoveRouting.Count = 0
        Set oRouting = mProcessDef.Routings(colRemoveRouting(1))
        colRemoveRouting.Remove 1
        mProcessDef.Routings.Remove oRouting.Guid
        FlowGUI.Nodes(oRouting.TaskDest.Guid).InLinks.Remove oRouting.Guid
    
    Loop
    
        
    '# remove nodes
    Do Until FlowGUI.SelNodes.Count = 0
        Set oTaskDef = mProcessDef.Tasks(FlowGUI.SelNodes(1).key)
        mProcessDef.Tasks.Remove oTaskDef.Guid
        FlowGUI.Nodes.Remove oTaskDef.Guid
    Loop
    Call Sanitize
    DeleteSelected = True
    Exit Function
Err_Raise:
    Call ErrRaise(Err, mcstrModule, "IContextMenu_CommandClick")
    
End Function
'/ copies the selected nodes and routing
Private Function CopySelected() As Boolean
    '/r TRUE if the selection could be copied (cannot copy routing when destination steps is not selected)
    Const cstrFunc = "CopySelected"
    On Error GoTo err_handler
    
    Dim oNewProcess As ProcessDef
    Dim oNode As afNode
    Dim oLink As afLink
    Dim oTaskDef As TaskDef
    Dim oRoutingDef As RoutingDef
    Dim oPT As AddFlow4Lib.afLinkPoint
    Dim oFlowExp As ACGWFDXML.XMLProcessDef
    Dim oNewTask As TaskDef
    Dim oRoot As MSXML2.IXMLDOMNode
    Dim sglOffsetX As Single
    Dim sglOffsetY As Single
    Dim oProp As Property
    sglOffsetX = 99999999999999#
    sglOffsetY = 99999999999999#
    
    Set oNewProcess = New ProcessDef
    
    For Each oNode In FlowGUI.SelNodes
        Set oTaskDef = mProcessDef.Tasks(oNode.key)
        
        Set oNewTask = oNewProcess.Tasks.Add(oTaskDef.Guid)
        
        With oNewTask
            .Left = oNode.Left
            .Top = oNode.Top
            .Width = oNode.Width
            .Height = oNode.Height
            If .Left < sglOffsetX Then sglOffsetX = .Left
            If .Top < sglOffsetY Then sglOffsetY = .Top
            .TaskTemplate = oTaskDef.TaskTemplate
        End With
        CopyPropGroup oTaskDef.PropertyGroup, oNewTask.PropertyGroup, False, True
        
    Next
    
    If oNewProcess.Tasks.Count = 0 Then Exit Function
    
    Dim oTaskOrg As TaskDef
    Dim oTaskDest As TaskDef
    Dim oNewRouting As RoutingDef
    For Each oLink In FlowGUI.SelLinks
        Set oRoutingDef = mProcessDef.Routings(oLink.key)
        On Error Resume Next
        Set oTaskOrg = Nothing
        Set oTaskOrg = oNewProcess.Tasks(oLink.Org.key)
        On Error GoTo err_handler
        '/ we only copy the routing into the clipboard IF the source and dest tasks have also been selected
        If Not (oTaskOrg Is Nothing) Then
            On Error Resume Next
            Set oTaskDest = Nothing
            Set oTaskDest = oNewProcess.Tasks(oLink.Dst.key)
            On Error GoTo err_handler
            If Not (oTaskDest Is Nothing) Then
                ' all present and correct, make new GUID for routing to prevent paste errors
                Set oNewRouting = oNewProcess.Routings.Add(oTaskOrg, oTaskDest, CreateGUID)
                oNewRouting.ClearPoints
                For Each oPT In oLink.ExtraPoints
                    If Not IgnorePoint(oLink, oPT) Then
                        If oPT.X < sglOffsetX Then sglOffsetX = oPT.X
                        If oPT.y < sglOffsetY Then sglOffsetY = oPT.y
                        oNewRouting.AddPoint oPT.X, oPT.y
                    End If
                Next
                CopyPropGroup oRoutingDef.PropertyGroup, oNewRouting.PropertyGroup, False, True
            End If
        End If
    Next
    
    Set oRoot = XMLDoc("ACGWFD.XMLClip")
    
    Set oFlowExp = New ACGWFDXML.XMLProcessDef
    
    oFlowExp.ProcessXML oNewProcess, oRoot
    
    XMLAttr oRoot, "OffsetX", sglOffsetX
    XMLAttr oRoot, "OffsetY", sglOffsetY
    
    Clipboard.Clear
    Clipboard.SetText oRoot.ownerDocument.xml
    
    CopySelected = True
    
    Exit Function
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Function
    End Select
    
End Function
    
'/ pastes data in from the clipboard
Private Function Paste() As Boolean
    Const cstrFunc = "Paste"
    On Error GoTo err_handler
    
    Dim oXML As MSXML2.DOMDocument
    Dim oRoot As MSXML2.IXMLDOMNode
    Dim oNewProcess As ProcessDef
    Dim oImport As ACGWFDXML.XMLProcessDef
    Dim oTaskDef As TaskDef
    Dim oRoutingDef As RoutingDef
    Dim strMappedXML As String
    Dim sglOffsetX As Single
    Dim sglOffsetY As Single
    Dim lngCount As Long
    Dim sglX As Single
    Dim sglY As Single
    
    '# collection to hold mapping between original GUIDs and new GUIDs
    Dim colGUIDMap As Collection
    
    Set oXML = New MSXML2.DOMDocument
    
    If Not oXML.loadXML(Clipboard.GetText) Then Exit Function
        
    Set oRoot = oXML.firstChild
    
    If oRoot.nodeName <> "ACGWFD.XMLClip" Then Exit Function
        
    sglOffsetX = (oRoot.Attributes.getNamedItem("OffsetX").nodeValue - msglLastX) - FlowGUI.xScroll
    sglOffsetY = (oRoot.Attributes.getNamedItem("OffsetY").nodeValue - msglLastY) - FlowGUI.yScroll
    
    Set oNewProcess = New ProcessDef
    '/ ensure that data we'll paste into the new process is mapped correctly to the process template
    oNewProcess.ProcessTemplate = mProcessDef.ProcessTemplate
    
    Set oImport = New ACGWFDXML.XMLProcessDef
    
    
    If Not oImport.XMLProcess(oNewProcess, oRoot.firstChild, moProcessTemplates, moTaskTemplates) Then Exit Function
    
    '# alter the GUIDs of each task and routing
    '# need to create a seperate collection as we are altering the keys
    '# of the Tasks collection and Enums / counting wont work!
    Dim colAlterGUID As Collection
    Set colAlterGUID = New Collection
    
    For Each oTaskDef In oNewProcess.Tasks
        colAlterGUID.Add oTaskDef
    Next
    
    Do Until colAlterGUID.Count = 0
        Set oTaskDef = colAlterGUID(1)
        colAlterGUID.Remove 1
        oTaskDef.Guid = CreateGUID
    Loop
    
    For Each oRoutingDef In oNewProcess.Routings
        colAlterGUID.Add oRoutingDef
    Next
    
    Do Until colAlterGUID.Count = 0
        Set oRoutingDef = colAlterGUID(1)
        colAlterGUID.Remove 1
        oRoutingDef.Guid = CreateGUID
    Loop
    '# loop through flow and deselect everything ready for adding the new nodes
    Dim oNode As afNode
    Dim oLink As afLink
    For Each oNode In FlowGUI.Nodes
        If oNode.Selected Then oNode.Selected = False
        For Each oLink In oNode.Links
            If oLink.Selected Then oLink.Selected = False
        Next
    Next

    '# add the nodes

    Dim oNewTask As TaskDef
    
    For Each oTaskDef In oNewProcess.Tasks
        Set oNewTask = mProcessDef.Tasks.Add(oTaskDef.Guid)
        '# copy common prop groups from this flow's template first
        CopyPropGroup moSettings.CommonTaskProperties, oNewTask.PropertyGroup, False, True
        '# now copy prop groups from copied task
        CopyPropGroup oTaskDef.PropertyGroup, oNewTask.PropertyGroup, False, True
        With oNewTask
            .Height = oTaskDef.Height
            .Left = oTaskDef.Left
            .TaskTemplate = oTaskDef.TaskTemplate
            .Top = oTaskDef.Top
            .Width = oTaskDef.Width
        End With
        Set oNode = AddGUINode(oNewTask, sglOffsetX, sglOffsetY)
        oNode.Selected = True
    Next
    
    Dim oNewRouting As RoutingDef
    
    For Each oRoutingDef In oNewProcess.Routings
        Set oNewRouting = mProcessDef.Routings.Add(mProcessDef.Tasks(oRoutingDef.TaskOrg.Guid), mProcessDef.Tasks(oRoutingDef.TaskDest.Guid), oRoutingDef.Guid)
        oNewRouting.Name = oRoutingDef.Name
        oNewRouting.Parallel = oRoutingDef.Parallel
        '# copy common prop groups from this flow's template first
        CopyPropGroup moSettings.CommonRoutingProperties, oNewRouting.PropertyGroup, False, True
        '# now copy properties set in copied task
        CopyPropGroup oRoutingDef.PropertyGroup, oNewRouting.PropertyGroup, False, True
        
        '# need to copy points
        For lngCount = 1 To oRoutingDef.PointCount
            oRoutingDef.Point sglX, sglY, lngCount
            oNewRouting.AddPoint sglX - sglOffsetX, sglY - sglOffsetY
        Next
        Set oLink = AddGUIRouting(oNewRouting)
        oLink.Selected = True
    Next
    
    Call Sanitize
    Paste = True
    Exit Function
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Function
    End Select
    

End Function

Private Sub ExportImage()
    Const cstrFunc = "ExportImage"
    On Error GoTo err_handler
    
    Dim dlg As MSComDlg.CommonDialog
    
    Set dlg = Parent.dlg
    dlg.Filter = "Windows MetaFile|*.wmf|Enhanced Windows MetaFile|*.emf"
    dlg.FilterIndex = 1
    dlg.DialogTitle = "Export Flow Image"
    dlg.fileName = mProcessDef.Name
    dlg.Flags = MSComDlg.cdlOFNOverwritePrompt
    On Error Resume Next
    dlg.ShowSave
    If Err.Number <> 0 Then Exit Sub
    On Error GoTo err_handler
    
    SaveImage dlg.fileName
    MsgBox "Export Complete"
    
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Public Property Get ProcessDef() As ACGProcessDefs.ProcessDef
    Set ProcessDef = mProcessDef
End Property

Public Sub SaveImage(fileName As String)
    On Error GoTo err_handler
    Const cstrFunc = "SaveImage"
    If Len(Dir$(fileName)) > 0 Then
        Kill fileName
    End If
        
    If StrComp(Right$(fileName, 4), ".emf", vbTextCompare) Then
        FlowGUI.SaveImage afTypeMediumFile, afEMF, fileName
    Else
        FlowGUI.SaveImage afTypeMediumFile, afWMF, fileName
    End If
    
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub
Private Sub ShowPropWin()
    Dim oTaskDef As TaskDef
    Dim oRouting As RoutingDef
    Dim oDW As DockWindowForm
    
    Set oDW = Parent.ds.DockWindows.GetForm("dwProperties")
    Set moPropList = oDW.Form
    
    If Not (FlowGUI.SelectedNode Is Nothing) Then
        Set oTaskDef = mProcessDef.Tasks(FlowGUI.SelectedNode.key)
        Set moPropList.PropBag = oTaskDef.PropertyGroup
        oDW.Caption = "Task"
    ElseIf Not (FlowGUI.SelectedLink Is Nothing) Then
        Set oRouting = mProcessDef.Routings(FlowGUI.SelectedLink.key)
        Set moPropList.PropBag = oRouting.PropertyGroup
        oDW.Caption = "Routing"
    Else
        Set moPropList.PropBag = mProcessDef.PropertyGroup
        oDW.Caption = "Process"
    End If
    moPropList.init moParent, moTaskTemplates, moProcessTemplates
End Sub
Public Function LoadFlow(fileName As String, Optional showVersions As Boolean = True) As Boolean
    Const cstrFunc = "LoadFlow"
    On Error GoTo err_handler
    Dim oLoad As XMLProcessVersion
    Set oLoad = New XMLProcessVersion
    Set moVersions = New Versions
    mstrFileName = fileName
    If Not oLoad.FileLoadXML(fileName, moVersions, moTaskTemplates, moProcessTemplates) Then
        '/ try the old loader
        Dim oImport As XMLProcessDef
        Set oImport = New XMLProcessDef
        Set mProcessDef = New ProcessDef
        If Not (oImport.FileLoadXML(fileName, mProcessDef, moTaskTemplates, moProcessTemplates)) Then
            MsgBox "Failed to load process!", vbExclamation
            LoadFlow = False
            Exit Function
        End If
        If MsgBox("Process was from an older version. Convert?", vbYesNo + vbQuestion) = vbNo Then
            MsgBox "Failed to load process!", vbExclamation
            LoadFlow = False
            Exit Function
        
        End If
        
        '/ add original GUID's as properties for conversion
        Call AddGUIDForConvert(mProcessDef)
        Kill mstrFileName
        oLoad.FileSaveXML mstrFileName, moVersions, mProcessDef
    Else
        '// pop up versions dialog
        If (showVersions) Then
            Set mProcessVersion = frmVersions.showVersions(moVersions)
            mForUpdate = frmVersions.forUpdate
        Else
            Set mProcessVersion = moVersions(moVersions.MaxVer)
            mForUpdate = False
        End If
        Set mProcessDef = mProcessVersion.ProcessDef
        '/Set mProcessDef = oVersions(oVersions.MaxVer).ProcessDef
    End If
    
    
    '# make sure we have the settings for this flow loaded
    
    Set moSettings = moProcessTemplates(mProcessDef.ProcessTemplate)
    
    '# now create steps + routing in gui
    
    Call LoadFromFlow
    LoadFlow = True
    Exit Function
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Function
    End Select
End Function
'/ reads the definitions held in mFlow and creates the GUI images
Private Sub LoadFromFlow()
    Dim oTaskDef As TaskDef
    Dim oRouting As RoutingDef
    
    FlowGUI.Nodes.Clear
    
    For Each oTaskDef In mProcessDef.Tasks
        AddGUINode oTaskDef
    Next
    For Each oRouting In mProcessDef.Routings
        AddGUIRouting oRouting
    Next
    
    Call Sanitize
    FlowGUI.SetChangedFlag False
    
End Sub

Private Function IgnorePoint(oLink As afLink, oPT As afLinkPoint) As Boolean
    '# ignore 1st point
    
    IgnorePoint = oPT.X = oLink.ExtraPoints(0).X And oPT.y = oLink.ExtraPoints(0).y
    Exit Function
    Dim oSrc As TaskDef
    Dim oDst As TaskDef
    Set oSrc = mProcessDef.Tasks(oLink.Org.key)
    Set oDst = mProcessDef.Tasks(oLink.Dst.key)
    
    IgnorePoint = TouchesStep(oSrc, oPT) Or TouchesStep(oDst, oPT)
End Function

Private Function TouchesStep(oTaskDef As TaskDef, oPT As afLinkPoint) As Boolean
    TouchesStep = (oPT.X = oTaskDef.Left Or oPT.X = oTaskDef.Width + oTaskDef.Left Or oPT.y = oTaskDef.Top Or oPT.y = oTaskDef.Top + oTaskDef.Height)
End Function

Private Sub SaveFlow(saveAs As Boolean)
    Const cstrFunc = "SaveFlow"
    Dim strErrFunc As String
    strErrFunc = "Initialisation"
    On Error GoTo err_handler
    Call Sanitize
    If mProcessDef.isValid = False Then
        MsgBox "Warning - the current flow is not valid will not work correctly in the engine", vbExclamation
    End If
    
    Dim oNode As afNode
    Dim oTaskDef As TaskDef
    Dim oPT As AddFlow4Lib.afLinkPoint
    Dim oLink As AddFlow4Lib.afLink
    Dim oRouting As RoutingDef
    Dim lngPointCount As Long
    
    strErrFunc = "Parse Nodes"
    For Each oNode In FlowGUI.Nodes
        Set oTaskDef = mProcessDef.Tasks(oNode.key)
        With oTaskDef
            .Left = oNode.Left
            .Top = oNode.Top
            .Width = oNode.Width
            .Height = oNode.Height
        End With
        
    Next
    For Each oTaskDef In mProcessDef.Tasks
        Set oNode = FlowGUI.Nodes(oTaskDef.Guid)
        For Each oLink In oNode.OutLinks
            Set oRouting = mProcessDef.Routings(oLink.key)
            oRouting.ClearPoints
            For Each oPT In oLink.ExtraPoints
                If Not IgnorePoint(oLink, oPT) Then
                    oRouting.AddPoint oPT.X, oPT.y
                End If
            Next
        Next
    Next
    strErrFunc = "Save Native Format"
    
    Dim oExport As XMLProcessVersion
    Dim oVersions As Versions
    Set oVersions = New Versions
    
    Set oExport = New XMLProcessVersion
    If saveAs Then
        Dim dlg As MSComDlg.CommonDialog
        
        Set dlg = Parent.dlg
        dlg.Filter = "ACG WorkFlow Format|*.acgwfd.xml"
        dlg.FilterIndex = 1
        dlg.DialogTitle = "New Process"
        dlg.fileName = "Copy of " & mProcessDef.Name & " Process"
        dlg.Flags = MSComDlg.cdlOFNOverwritePrompt
        On Error Resume Next
        dlg.ShowSave
        If Err.Number <> 0 Then Exit Sub
        On Error GoTo err_handler
        strErrFunc = "Deleting existing file"
        If Len(Dir$(dlg.fileName)) > 0 Then
            Kill dlg.fileName
        End If
        
        strErrFunc = "Exporting new file"
        mProcessDef.Name = Left$(dlg.FileTitle, Len(dlg.FileTitle) - Len(".acgwfd.xml"))
        oExport.FileSaveXML dlg.fileName, oVersions, mProcessDef
        Caption = getCaption
        Parent.ds.ActiveDocumentWindow.Caption = mProcessDef.Name
    ElseIf mForUpdate Then
        '// update the version with a new revision
        '// TODO
        'oExport.FileLoadXML mstrFileName, oVersions, moTaskTemplates, moProcessTemplates
        'oExport.FileSaveXML mstrFileName, oVersions, mProcessDef
        MsgBox "ERROR: can't save an updated process yet!!!! File has NOT been saved!", vbCritical
    Else
        oExport.FileLoadXML mstrFileName, oVersions, moTaskTemplates, moProcessTemplates
        oExport.FileSaveXML mstrFileName, oVersions, mProcessDef
    End If
    FlowGUI.SetChangedFlag False
    
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc, strErrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Function AddGUINode(oTaskDef As TaskDef, Optional OffsetX As Single = 0, Optional OffsetY As Single = 0) As afNode
    Const cstrFunc = "AddGUINode"
    On Error GoTo err_handler
    
    '/ create a GUI node from a FlowNode class
    Dim oNode As AddFlow4Lib.afNode
    Set oNode = FlowGUI.Nodes.Add(oTaskDef.Left - OffsetX, oTaskDef.Top - OffsetY, oTaskDef.Width, oTaskDef.Height)
    With oNode
        .Text = NodeCaption(oTaskDef)
        Set .Picture = LoadPicture(App.Path & mcstrImagesPath & moTaskTemplates(oTaskDef.TaskTemplate).Icon)
        .key = oTaskDef.Guid
        .xTextMargin = 4
        .yTextMargin = 4
    End With
    Set AddGUINode = oNode
    Exit Function
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Function
    End Select

End Function

Private Function AddGUIRouting(oRouting As RoutingDef, Optional OffsetX As Single = 0, Optional OffsetY As Single = 0) As afLink
    '/ create routing in the GUI from a FlowRouting class
    Dim oLink As AddFlow4Lib.afLink
    Dim oTaskDef As TaskDef
    Dim lngPointCount As Long, sglX As Single, sglY As Single
    Dim oPT As afLinkPoint
    
    '# add the link in the GUI
    Set oLink = FlowGUI.Nodes(oRouting.TaskOrg.Guid).OutLinks.Add(FlowGUI.Nodes(oRouting.TaskDest.Guid))
    
    With oLink
        .Text = oRouting.Name
        .key = oRouting.Guid
    End With
    
    '# add any additional points to the GUI link line as required
    If oRouting.PointCount = 0 Then
        For Each oPT In oLink.ExtraPoints
            If Not IgnorePoint(oLink, oPT) Then
                oRouting.AddPoint oPT.X, oPT.y
            End If
        Next
    Else
        '# add some temporary extra points to the line
        
        lngPointCount = oRouting.PointCount
        If lngPointCount > 1 Then
            '# if there is more than one point we need to add an extra point to the total we create
            lngPointCount = lngPointCount + 1
        End If
        
        Do Until oLink.ExtraPoints.Count >= lngPointCount
            oLink.ExtraPoints.Add oRouting.TaskDest.Left - OffsetX, oRouting.TaskDest.Top - OffsetY
        Loop
        
        '# now move them into the correct positions
        For lngPointCount = 1 To oRouting.PointCount
            oRouting.Point sglX, sglY, lngPointCount
            'Debug.Print "Moving Point", sglX, sglY
            Set oPT = oLink.ExtraPoints(lngPointCount)
            oPT.X = sglX - OffsetX
            oPT.y = sglY - OffsetY
            Set oLink.ExtraPoints.Item(lngPointCount) = oPT
        Next
    End If
    Set AddGUIRouting = oLink
End Function

Private Sub IContextMenu_Deactivate()
    Set moPropList = Nothing
End Sub

Private Property Get IContextMenu_ProcessDef() As ACGProcessDefs.ProcessDef
    Set IContextMenu_ProcessDef = mProcessDef
End Property

Private Sub IContextMenu_QueryUnload(Cancel As Boolean)
    If FlowGUI.IsChanged Then
        Select Case MsgBox("Flow has changed. Do you want to save?", vbYesNoCancel + vbQuestion)
            Case vbCancel
                Cancel = True
            Case vbYes
                Call SaveFlow(False)
        End Select
    End If
End Sub

Private Sub PrintFlow()
    Const cstrFunc = "PrintFlow"
    On Error GoTo err_handler
    prn.hWndFlow = FlowGUI.hWnd

    Dim strName As String
    'strName = mProcessDef.PropertyGroup.Item("CTMS").Item("Display Name").Value
    'If Len(strName) = 0 Then
        strName = mProcessDef.Name
    'End If
    
    prn.DocName = strName


    'PrnFlow1.PageBorder = PageBorderDottedBoxDot

    ' The header contains the file name (placed at the left)
    ' and the date (placed at the right)

    prn.Header = strName & "||" & Format(Date, "dd mmm yyyy")

    ' The footer contains the page number (placed at the center)

    prn.Footer = "|- Page <PAGE> -|"

    'prn.ForeColor = vbBlue

    ' Indicates that the output will be sent to the printer

    prn.Preview = False

    ' show printer settings box
    prn.PrinterSettings = True
    ' fit to page
    prn.FitToPage = True
    ' Print the AddFlow diagram
    FlowGUI.ShowGrid = False
    
    prn.PrintDoc
    FlowGUI.ShowGrid = True
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub FindData()
    Set frmFind.Flow = FlowGUI
    frmFind.Show vbModal
    
End Sub

'/ spellchecks the flow using the craft approach of calling Excel's spellchecker...
'/ calls Excel late bound, so as to not fail on machines that dont have excel installed and to be version independant
Private Sub SpellCheck()
    Const cstrFunc = "SpellCheck"
    On Error GoTo err_handler
    
    Dim oXLApp As Object
    Dim oXLBook As Object
    Dim oXLSheet As Object
    Dim oTaskDef As TaskDef
    Dim oRoutingDef As RoutingDef
    Dim lngCount As Long
    
    Set oXLApp = CreateObject("Excel.Application")
    Set oXLBook = oXLApp.WorkBooks.Add
    Set oXLSheet = oXLBook.WorkSheets.Add
    FlowGUI.SelNodes.Clear
    FlowGUI.SelLinks.Clear
    For Each oTaskDef In mProcessDef.Tasks
        
        oXLSheet.Cells(1, 1).Value = oTaskDef.Name
        With FlowGUI.Nodes(oTaskDef.Guid)
            .Selected = True
            .EnsureVisible
        End With
        oXLSheet.CheckSpelling
        oTaskDef.Name = oXLSheet.Cells(1, 1).Value
        With FlowGUI.Nodes(oTaskDef.Guid)
            .Text = NodeCaption(oTaskDef)
            .Selected = False
        End With
        
        For Each oRoutingDef In oTaskDef.RoutingOut
            oXLSheet.Cells(1, 1).Value = oRoutingDef.Name
            With FlowGUI.Nodes(oTaskDef.Guid).OutLinks(oRoutingDef.Guid)
                .Selected = True
                .EnsureVisible
            End With
            oXLSheet.CheckSpelling
            oRoutingDef.Name = oXLSheet.Cells(1, 1).Value
            With FlowGUI.Nodes(oTaskDef.Guid).OutLinks(oRoutingDef.Guid)
                .Selected = False
                .Text = oRoutingDef.Name
            End With
            
        Next
        
    Next
    
    Set oXLSheet = Nothing
    oXLBook.Close 0
    Set oXLBook = Nothing
    oXLApp.Application.Quit
    Set oXLApp = Nothing
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub IContextMenu_Refresh()
    Sanitize
    ShowPropWin
    Dim oNode As afNode
    Dim oTaskDef As TaskDef
    '/ reset all captions in case properties have been changed
    For Each oNode In FlowGUI.Nodes
        Set oTaskDef = mProcessDef.Tasks(oNode.key)
        oNode.Text = NodeCaption(oTaskDef)
    Next
    FlowGUI.Refresh
End Sub

Private Sub moPropList_PropChanged(oProperty As Property)
    If Not (FlowGUI.SelectedNode Is Nothing) Then
        FlowGUI.SelectedNode.Text = NodeCaption(mProcessDef.Tasks(FlowGUI.SelectedNode.key))
    ElseIf Not (FlowGUI.SelectedLink Is Nothing) Then
        FlowGUI.SelectedLink.Text = mProcessDef.Routings(FlowGUI.SelectedLink.key).Name
    Else
        '# flow properties
        Parent.ds.ActiveDocumentWindow.Caption = mProcessDef.Name
    End If
    Call Sanitize
End Sub

Public Property Get forUpdate() As Boolean
    forUpdate = mForUpdate
End Property

Public Property Get getCaption() As String
     getCaption = mProcessDef.Name & " v." & mProcessVersion.version & IIf(mForUpdate, " [UPDATING]", "")
End Property
