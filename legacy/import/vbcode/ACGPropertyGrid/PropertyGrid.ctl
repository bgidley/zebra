VERSION 5.00
Object = "{C0A63B80-4B21-11D3-BD95-D426EF2C7949}#1.0#0"; "vsflex7l.ocx"
Begin VB.UserControl PropertyGrid 
   ClientHeight    =   5580
   ClientLeft      =   0
   ClientTop       =   0
   ClientWidth     =   6090
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   ScaleHeight     =   5580
   ScaleWidth      =   6090
   Begin VSFlex7LCtl.VSFlexGrid fg 
      Height          =   3810
      Left            =   540
      TabIndex        =   0
      Top             =   360
      Width           =   3030
      _cx             =   5345
      _cy             =   6720
      _ConvInfo       =   1
      Appearance      =   1
      BorderStyle     =   1
      Enabled         =   -1  'True
      BeginProperty Font {0BE35203-8F91-11CE-9DE3-00AA004BB851} 
         Name            =   "Tahoma"
         Size            =   8.25
         Charset         =   0
         Weight          =   400
         Underline       =   0   'False
         Italic          =   0   'False
         Strikethrough   =   0   'False
      EndProperty
      MousePointer    =   0
      BackColor       =   -2147483643
      ForeColor       =   -2147483640
      BackColorFixed  =   -2147483633
      ForeColorFixed  =   -2147483630
      BackColorSel    =   -2147483635
      ForeColorSel    =   -2147483634
      BackColorBkg    =   -2147483636
      BackColorAlternate=   -2147483643
      GridColor       =   -2147483633
      GridColorFixed  =   -2147483632
      TreeColor       =   -2147483632
      FloodColor      =   192
      SheetBorder     =   -2147483642
      FocusRect       =   1
      HighLight       =   1
      AllowSelection  =   -1  'True
      AllowBigSelection=   -1  'True
      AllowUserResizing=   0
      SelectionMode   =   0
      GridLines       =   1
      GridLinesFixed  =   2
      GridLineWidth   =   1
      Rows            =   50
      Cols            =   10
      FixedRows       =   1
      FixedCols       =   1
      RowHeightMin    =   0
      RowHeightMax    =   0
      ColWidthMin     =   0
      ColWidthMax     =   0
      ExtendLastCol   =   0   'False
      FormatString    =   ""
      ScrollTrack     =   0   'False
      ScrollBars      =   3
      ScrollTips      =   0   'False
      MergeCells      =   0
      MergeCompare    =   0
      AutoResize      =   -1  'True
      AutoSizeMode    =   0
      AutoSearch      =   0
      AutoSearchDelay =   2
      MultiTotals     =   -1  'True
      SubtotalPosition=   1
      OutlineBar      =   0
      OutlineCol      =   0
      Ellipsis        =   0
      ExplorerBar     =   0
      PicturesOver    =   0   'False
      FillStyle       =   0
      RightToLeft     =   0   'False
      PictureType     =   0
      TabBehavior     =   0
      OwnerDraw       =   0
      Editable        =   0
      ShowComboButton =   -1  'True
      WordWrap        =   0   'False
      TextStyle       =   0
      TextStyleFixed  =   0
      OleDragMode     =   0
      OleDropMode     =   0
      ComboSearch     =   3
      AutoSizeMouse   =   -1  'True
      FrozenRows      =   0
      FrozenCols      =   0
      AllowUserFreezing=   0
      BackColorFrozen =   0
      ForeColorFrozen =   0
      WallPaperAlignment=   9
   End
   Begin VB.Image imgFile 
      Enabled         =   0   'False
      Height          =   240
      Left            =   4260
      Picture         =   "PropertyGrid.ctx":0000
      Top             =   2100
      Visible         =   0   'False
      Width           =   240
   End
End
Attribute VB_Name = "PropertyGrid"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
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
Private mPropertyGroup As PropertyGroup
Event PropChanged(ByRef oProperty As Property)
Event PropRemoved(ByRef oProperty As Property)
Event TextPopup(ByRef oProperty As Property, ByRef Cancel As Boolean)
Event FileBrowse(ByRef oProperty As Property, ByRef FileName As String, ByRef Cancel As Boolean)
Event ContextClick(ByRef oProperty As Property, X As Single, Y As Single)
Private mfDontRefresh As Boolean
Private mfRefreshRequest As Boolean
Private mButton As Integer
Private mX As Single
Private mY As Single
Private mfRefreshing As Boolean
Private mfShowLocked As Boolean

Public Property Get ShowLocked() As Boolean
    ShowLocked = mfShowLocked
End Property

Public Property Let ShowLocked(v As Boolean)
    mfShowLocked = v
    Refresh
End Property

Private Sub fg_CellChanged(ByVal Row As Long, ByVal Col As Long)
    If mfRefreshing Then Exit Sub
    If mPropertyGroup Is Nothing Then Exit Sub
    Dim oProp As Property
    Dim strValue As String
    
    If Col <> 3 Or Row < 1 Then Exit Sub
    If fg.EditWindow <> 0 Then
        strValue = fg.EditText
    Else
        strValue = fg.Cell(flexcpText, Row, 3)
    End If
    Set oProp = fg.RowData(Row)
    oProp.Value = strValue
    RaiseEvent PropChanged(oProp)
    If mfRefreshRequest Then Refresh
End Sub


Private Sub fg_Click()
    If mButton = vbRightButton And fg.IsSubtotal(fg.Row) = False Then
        If fg.MouseCol > 0 And fg.MouseRow > 0 Then
        If Not fg.IsSubtotal(fg.MouseRow) Then
            Debug.Print fg.MouseCol, fg.MouseRow
            fg.Select fg.MouseRow, fg.MouseCol
            RaiseEvent ContextClick(fg.RowData(fg.Row), mX, mY)
        End If
        End If
    End If

End Sub


Private Sub fg_MouseUp(Button As Integer, Shift As Integer, X As Single, Y As Single)
    mButton = Button
    mX = X
    mY = Y
End Sub



Private Sub UserControl_Initialize()
    ' initialize control
    fg.Rows = 1                                 ' start empty
    fg.Cols = 4                                 ' outline, category, property, value
    fg.TextMatrix(0, 2) = "Property"            ' column titles
    fg.TextMatrix(0, 3) = "Value"               ' column titles
    fg.Editable = flexEDKbd                     ' double-clicks start editing
    'fg.OwnerDraw = flexODOver                   ' use ownerdraw to show colors
    fg.OutlineCol = 0                           ' set outline column properties
    fg.ColWidth(0) = 230                        ' narrow outline column
    fg.OutlineBar = flexOutlineBarSymbolsLeaf   ' no tree, just symbols
    fg.ColHidden(1) = True                      ' hide categories
    fg.MergeCells = flexMergeSpill              ' allow categories to spill into property column
    fg.ColAlignment(-1) = flexAlignLeftTop      ' align all to left
    fg.AllowSelection = False                   ' select a single cell at a time
    fg.AllowUserResizing = flexResizeColumns    ' give user freedom
    fg.ScrollTrack = True                       ' scroll as the user drags the scroll thumb
    fg.FixedCols = 0                            ' to look nice
    fg.ExtendLastCol = True
    fg.Ellipsis = flexEllipsisEnd
    fg.BackColorBkg = fg.GridColor
    fg.HighLight = flexHighlightNever
    
    
End Sub

Public Sub Refresh()
    If mfDontRefresh Then
        mfRefreshRequest = True
        Exit Sub
    End If
    Dim oProp As Property
    Dim oProps As Properties
    mfRefreshing = True
    Dim fShow As Boolean
    mfRefreshRequest = False
    With fg
        .Rows = 1
        If Not (mPropertyGroup Is Nothing) Then
            For Each oProps In mPropertyGroup
                For Each oProp In oProps
                    If oProp.Locked Then
                        fShow = mfShowLocked
                    Else
                        fShow = True
                    End If
                    If fShow Then
                        .AddItem vbTab & oProps.Name & vbTab & oProp.Name & vbTab & FriendlyValue(oProp)
                        .RowData(.Rows - 1) = oProp
                    End If
                Next
            Next
            
        End If
        ' do an autosize on property names
        .AutoSize .Cols - 2, , , 300
    End With
    ' initialize display
    DisplayCategorized
    
    mfRefreshing = False
End Sub
Private Function FriendlyValue(oProperty As Property) As String
    Select Case oProperty.PropertyType
        Case ptBoolean
            FriendlyValue = Format$(oProperty.Value, "Yes/No")
        Case Else
            FriendlyValue = oProperty.Value
    End Select
End Function
Private Sub UserControl_Resize()
    On Error Resume Next
    fg.Move 0, 0, ScaleWidth, ScaleHeight
End Sub

Public Property Set PropertyGroup(v As PropertyGroup)
    If fg.EditWindow <> 0 Then
        '# force the property to be saved
        Call fg_CellChanged(fg.Row, fg.Col)
    End If
    Set mPropertyGroup = v
    '# refresh the control
    Refresh
End Property

Public Property Get PropertyGroup() As PropertyGroup
    Set PropertyGroup = mPropertyGroup
End Property

Public Property Get Selected() As Property
    If fg.IsSubtotal(fg.Row) Then
        Set Selected = Nothing
    Else
        Set Selected = fg.RowData(fg.Row)
    End If
End Property


'##############################################################################
'# COPIED CODE
'##############################################################################
Private Sub DisplayCategorized()
    If fg.Rows = 1 Then Exit Sub
    ' freeze to avoid flicker
    fg.Redraw = flexRDNone
    
    ' remove any existing subtotals (groups)
    fg.Subtotal flexSTClear
    
    ' sort by category, then by property name
    fg.Select 1, 1, 1, 2
    fg.Sort = flexSortStringAscending
    
    ' add subtotals (groups) by category (col 1)
    fg.Subtotal flexSTNone, 1, , , fg.GridColor, , True
    
    ' show outline column
    fg.ColHidden(0) = False
    
    ' to look nice
    fg.GridLines = flexGridFlatVert
    
    ' reset display
    
    fg.TopRow = 1
    fg.Select 2, fg.Cols - 1
    fg.Redraw = flexRDBuffered

End Sub

Private Sub DisplayAlphabetic()
    
    ' freeze to avoid flicker
    fg.Redraw = flexRDNone
    
    ' remove any existing subtotals (groups)
    fg.Subtotal flexSTClear
    
    ' sort by property name
    fg.Col = 2
    fg.Sort = flexSortStringAscending
    
    ' hide outline column
    fg.ColHidden(0) = True
    
    ' to look nice
    fg.GridLines = flexGridFlat
    
    ' reset display
    fg.TopRow = 1
    fg.Select 1, fg.Cols - 1
    fg.Redraw = flexRDBuffered

End Sub

Private Sub fg_BeforeEdit(ByVal Row As Long, ByVal Col As Long, Cancel As Boolean)
    
    ' we can't edit total rows or label columns
    If fg.IsSubtotal(Row) Or Col <> fg.Cols - 1 Then
        Cancel = True
        Exit Sub
    End If
    
    ' assume regular editing
    fg.ComboList = ""
    Dim oProp As Property
    Set oProp = fg.RowData(Row)
    ' setup to edit based on property type
    Select Case oProp.PropertyType
    
        Case ptFile
            fg.ComboList = "..."
            fg.CellButtonPicture = imgFile
         
        Case ptString
            fg.ComboList = "..."
            fg.CellButtonPicture = imgFile
        
        Case ptBoolean
            fg.ComboList = "Yes|No"
    End Select

    ' use automatic double-click for editing text, manual for lists
    If Len(fg.ComboList) Then
        fg.Editable = flexEDKbd
    Else
        fg.Editable = flexEDKbdMouse
    End If

End Sub

Private Sub fg_BeforeRowColChange(ByVal OldRow As Long, ByVal OldCol As Long, ByVal NewRow As Long, ByVal NewCol As Long, Cancel As Boolean)

    ' user can select only the last column
    With fg
        If .Redraw <> flexRDNone And NewCol <> .Cols - 1 Then
            Cancel = True
            .Select NewRow, .Cols - 1
        End If
    End With
    
End Sub

Private Sub fg_BeforeUserResize(ByVal Row As Long, ByVal Col As Long, Cancel As Boolean)

    ' don't resize outline column
    If Col = 0 Then Cancel = True
    
End Sub

Private Sub fg_CellButtonClick(ByVal Row As Long, ByVal Col As Long)
    Dim oProp As Property
    Set oProp = fg.RowData(Row)
    If oProp.PropertyType = ptFile Then
        Dim strFileName As String
        Dim fCancel As Boolean
        mfDontRefresh = True
        mfRefreshRequest = False
        
        Select Case oProp.PropertyType
            Case ptFile
                On Error Resume Next
                RaiseEvent FileBrowse(oProp, strFileName, fCancel)
                If Not (fCancel = True Or Err.Number <> 0) Then
                    fg.TextMatrix(Row, fg.Cols - 1) = strFileName
                End If
                
        End Select
        mfDontRefresh = False
        If mfRefreshRequest Then Refresh
    ElseIf oProp.PropertyType = ptString Then
        Dim strText As String
        strText = oProp.Value
        RaiseEvent TextPopup(oProp, fCancel)
        If Not (fCancel = True Or Err.Number <> 0) Then
            fg.TextMatrix(Row, fg.Cols - 1) = oProp.Value
        End If
    End If
End Sub

Private Sub fg_DblClick()

    ' double-clicking on a group collapses/expands it
    Dim r%
    r = fg.MouseRow
    If r > -1 Then
        If fg.IsSubtotal(r) Then
            If fg.IsCollapsed(r) = flexOutlineCollapsed Then
                fg.IsCollapsed(r) = flexOutlineExpanded
            Else
                fg.IsCollapsed(r) = flexOutlineCollapsed
            End If
            fg.Tag = ""
            
        ' double-clicking on regular cells edits them
        Else
            fg.Tag = "*"
            fg.EditCell
        End If
    End If
End Sub

Private Sub fg_KeyDown(KeyCode As Integer, Shift As Integer)
    Dim r%
    Dim oProp As Property
    ' special handling for cursor keys
    Select Case KeyCode

        ' collapse/expand with cursor keys
        Case vbKeyLeft, vbKeyHome
            If fg.IsSubtotal(fg.Row) Then fg.IsCollapsed(fg.Row) = flexOutlineCollapsed
            If fg.Col <> fg.Cols - 1 Then fg.Col = fg.Cols - 1
            KeyCode = 0
        Case vbKeyRight, vbKeyEnd
            If fg.IsSubtotal(fg.Row) Then fg.IsCollapsed(fg.Row) = flexOutlineExpanded
            If fg.Col <> fg.Cols - 1 Then fg.Col = fg.Cols - 1
            KeyCode = 0
        Case vbKeyDelete
            If (Not fg.IsSubtotal(fg.Row)) And fg.Row > 0 Then
                Set oProp = fg.RowData(fg.Row)
                Select Case oProp.PropertyType
                    Case ptString, ptFile
                        oProp.Value = vbNullString
                        Refresh
                End Select
            End If
        ' when pushing control+ASCII, look for property
        Case Else
            If Shift >= 2 And KeyCode >= Asc("A") And KeyCode <= Asc("Z") Then
            
                ' look from current row down to bottom
                For r = fg.Row + 1 To fg.Rows - 1
                    If Not fg.RowHidden(r) Then
                        If UCase(Left(fg.TextMatrix(r, fg.Cols - 2), 1)) = Chr(KeyCode) Then
                            fg.Select r, fg.Cols - 1
                            fg.ShowCell r, fg.Cols - 1
                            KeyCode = 0
                            Exit For
                        End If
                    End If
                Next
                
                ' not found, so look from top down to current - 1
                For r = fg.FixedRows To fg.Row - 1
                    If Not fg.RowHidden(r) Then
                        If UCase(Left(fg.TextMatrix(r, fg.Cols - 2), 1)) = Chr(KeyCode) Then
                            fg.Select r, fg.Cols - 1
                            fg.ShowCell r, fg.Cols - 1
                            KeyCode = 0
                            Exit For
                        End If
                    End If
                Next
            End If
    End Select
    
End Sub

Private Sub fg_StartEdit(ByVal Row As Long, ByVal Col As Long, Cancel As Boolean)
    Dim strName As String
    strName = fg.Cell(flexcpText, Row, 2)
    Dim oProp As Property
    Set oProp = fg.RowData(Row)
    
    If oProp.Locked Then
        Cancel = True
        Exit Sub
    End If
    ' if this is a list, double-clicking selects the next item
    If Len(fg.Tag) > 0 And Len(fg.ComboList) > 0 And fg.ComboList <> "..." Then
        If ComboNext(Row, Col) Then Cancel = True
    End If
    fg.Tag = ""
    
End Sub

Private Function ComboNext(Row&, Col&) As Boolean

    ' get current list, trim combo pipe if any
    Dim s$, i%
    s = fg.ComboList
    If Left(s, 1) = "|" Then s = Mid(s, 2)
    
    ' look for current text in list, fail if not found
    i = InStr(s, fg.TextMatrix(Row, Col))
    If i <= 0 Then Exit Function
    
    ' look for next choice
    i = InStr(i, s, "|")
    If (i > 0) Then s = Mid(s, i + 1)
    
    ' trim excess
    i = InStr(s, "|")
    If i > 0 Then s = Left(s, i - 1)
    
    ' set new entry
    fg.TextMatrix(Row, Col) = s
    ComboNext = True
    
End Function

Private Sub optAlpha_Click()
    DisplayAlphabetic
End Sub

Private Sub optCat_Click()
    DisplayCategorized
End Sub

